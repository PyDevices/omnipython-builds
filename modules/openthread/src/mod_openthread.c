// SPDX-FileCopyrightText: 2026 Brad Barnett
//
// SPDX-License-Identifier: MIT

// openthread for MicroPython: a Thread network node on a chip with an
// IEEE 802.15.4 radio, through ESP-IDF's OpenThread.
//
//   import openthread
//   openthread.start()
//   openthread.dataset(openthread.dataset_new("bench", channel=15))
//   openthread.up(True)                    # forms the network, or joins it
//   openthread.role()                      # "detached", then "leader"
//   openthread.udp_open(4242)
//   openthread.udp_send("ff03::1", 4242, b"hello")
//   openthread.udp_recv()                  # ("fd00::...", 4242, b"hi") or None
//
// OpenThread runs in its own task, started by start(). Every call here takes
// OpenThread's lock for the time it reads or changes the stack, and none of
// them waits for the network: what arrives is queued until udp_recv() or
// discovered() reads it. The stack has no lwIP interface: UDP goes through
// OpenThread's own sockets, so Thread never becomes the board's default
// route and Wi-Fi's addresses, routes and DNS are left alone.

#include <string.h>

#include "py/mperrno.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "py/runtime.h"

#include "sdkconfig.h"

#if CONFIG_OPENTHREAD_ENABLED

#include "esp_heap_caps.h"
#include "esp_ieee802154.h"
#include "esp_openthread.h"
#include "esp_openthread_lock.h"
#include "esp_openthread_types.h"
#include "esp_vfs_eventfd.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "openthread/dataset.h"
#include "openthread/dataset_ftd.h"
#include "openthread/error.h"
#include "openthread/ip6.h"
#include "openthread/link.h"
#include "openthread/message.h"
#include "openthread/thread.h"
#include "openthread/udp.h"

// The most a udp_recv() datagram carries; longer ones are cut and counted.
#define OT_UDP_MAX 256
// How many datagrams wait for udp_recv(); the oldest is dropped when full.
#define OT_UDP_SLOTS 8
// How many networks one discover() remembers.
#define OT_FOUND_MAX 8

typedef struct {
    otIp6Address addr;
    uint16_t port;
    uint16_t len;
    uint8_t data[OT_UDP_MAX];
} ot_datagram_t;

typedef struct {
    otNetworkName name;
    otExtendedPanId extpanid;
    uint16_t panid;
    uint8_t channel;
    int8_t rssi;
} ot_found_t;

static bool s_started;
static otUdpSocket s_socket;
static bool s_socket_open;
static ot_datagram_t *s_inbox;  // OT_UDP_SLOTS of them, in PSRAM when there is some
static uint8_t s_head, s_count;
static uint32_t s_dropped, s_truncated;
static ot_found_t s_found[OT_FOUND_MAX];
static uint8_t s_found_count;
static bool s_discovering;

// --- helpers ------------------------------------------------------------------

static void ot_check(otError err) {
    if (err != OT_ERROR_NONE) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("OpenThread: %s"), otThreadErrorToString(err));
    }
}

static void ot_esp_check(esp_err_t err) {
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("OpenThread: %s"), esp_err_to_name(err));
    }
}

static otInstance *ot_lock(void) {
    if (!s_started) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("OpenThread isn't started: call openthread.start()"));
    }
    esp_openthread_lock_acquire(portMAX_DELAY);
    return esp_openthread_get_instance();
}

static void ot_unlock(void) {
    esp_openthread_lock_release();
}

static mp_obj_t ot_hex(const uint8_t *buf, size_t n) {
    static const char digits[] = "0123456789abcdef";
    char out[2 * 16];
    for (size_t i = 0; i < n; i++) {
        out[2 * i] = digits[buf[i] >> 4];
        out[2 * i + 1] = digits[buf[i] & 15];
    }
    return mp_obj_new_str(out, 2 * n);
}

static mp_obj_t ot_addr_str(const otIp6Address *addr) {
    char buf[OT_IP6_ADDRESS_STRING_SIZE];
    otIp6AddressToString(addr, buf, sizeof(buf));
    return mp_obj_new_str(buf, strlen(buf));
}

// --- start and stop -------------------------------------------------------------

// The OpenThread task is ours, not esp_openthread_start()'s. ESP-IDF creates
// its task inside an assert(), which a build without assertions (MicroPython's
// esp32 port) compiles out, and then waits forever for a task that was never
// made. It also stops the board on an init error instead of reporting it.
static esp_openthread_config_t s_config = {
    .platform_config = {
        .radio_config = { .radio_mode = RADIO_MODE_NATIVE },
        .host_config = { .host_connection_mode = HOST_CONNECTION_MODE_NONE },
        .port_config = {
            .storage_partition_name = "nvs",
            .netif_queue_size = 10,
            .task_queue_size = 10,
        },
    },
};
static SemaphoreHandle_t s_sync;      // given once init is done, and again when the task ends
static volatile esp_err_t s_init_err;

static void ot_task(void *arg) {
    (void)arg;
    s_init_err = esp_openthread_init(&s_config.platform_config);
    xSemaphoreGive(s_sync);
    if (s_init_err == ESP_OK) {
        esp_openthread_launch_mainloop();
        esp_openthread_deinit();
    }
    xSemaphoreGive(s_sync);
    vTaskDelete(NULL);
}

// openthread.start(): start the OpenThread task on the board's 802.15.4
// radio. Starting again does nothing. The network stays down until up(True).
static mp_obj_t ot_start(void) {
    if (s_started) {
        return mp_const_none;
    }
    // The task queue and the radio each wake OpenThread's main loop through
    // an eventfd. ESP-IDF registers the eventfd driver once; a second
    // register says so, which is fine.
    esp_vfs_eventfd_config_t eventfd_config = { .max_fds = 2 };
    esp_err_t err = esp_vfs_eventfd_register(&eventfd_config);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ot_esp_check(err);
    }
    // ESP-IDF's OpenThread doesn't check that the radio came up, and runs on
    // one that didn't. Bring the radio up once here, so one that fails raises.
    err = esp_ieee802154_enable();
    esp_ieee802154_disable();
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("OpenThread: the 802.15.4 radio didn't start (%s)"),
            esp_err_to_name(err));
    }
    if (s_sync == NULL) {
        s_sync = xSemaphoreCreateBinary();
        if (s_sync == NULL) {
            mp_raise_type(&mp_type_MemoryError);
        }
    }
    if (xTaskCreate(ot_task, CONFIG_OPENTHREAD_TASK_NAME, CONFIG_OPENTHREAD_TASK_SIZE, NULL,
        CONFIG_OPENTHREAD_TASK_PRIORITY, NULL) != pdPASS) {
        mp_raise_type(&mp_type_MemoryError);
    }
    // Init takes well under a second; ten mean it is stuck.
    if (xSemaphoreTake(s_sync, pdMS_TO_TICKS(10000)) != pdTRUE) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("OpenThread: the stack didn't start in 10 s"));
    }
    if (s_init_err != ESP_OK) {
        xSemaphoreTake(s_sync, portMAX_DELAY);  // the task has ended
        ot_esp_check(s_init_err);
    }
    s_started = true;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_start_obj, ot_start);

static void ot_udp_close_locked(otInstance *ot);

// openthread.stop(): leave the network and stop the OpenThread task. The
// dataset stays in flash.
static mp_obj_t ot_stop(void) {
    if (!s_started) {
        return mp_const_none;
    }
    otInstance *ot = ot_lock();
    ot_udp_close_locked(ot);
    otThreadSetEnabled(ot, false);
    otIp6SetEnabled(ot, false);
    ot_unlock();
    ot_esp_check(esp_openthread_mainloop_exit());
    xSemaphoreTake(s_sync, portMAX_DELAY);  // the task has ended
    s_started = false;
    s_discovering = false;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_stop_obj, ot_stop);

// --- the dataset ----------------------------------------------------------------

// openthread.dataset_new(name=None, channel=None, panid=None) -> bytes: a
// new network's dataset, with a random network key, as TLVs. It sets
// nothing: hand it to dataset() on this board and the others.
static mp_obj_t ot_dataset_new(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_name, ARG_channel, ARG_panid };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_name, MP_ARG_OBJ, {.u_obj = mp_const_none} },
        { MP_QSTR_channel, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = mp_const_none} },
        { MP_QSTR_panid, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = mp_const_none} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);

    const char *name = args[ARG_name].u_obj == mp_const_none ? NULL : mp_obj_str_get_str(args[ARG_name].u_obj);
    if (name != NULL && (strlen(name) == 0 || strlen(name) > OT_NETWORK_NAME_MAX_SIZE)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("a network name is 1 to %d bytes"), OT_NETWORK_NAME_MAX_SIZE);
    }
    int channel = -1, panid = -1;
    if (args[ARG_channel].u_obj != mp_const_none) {
        channel = mp_obj_get_int(args[ARG_channel].u_obj);
        if (channel < 11 || channel > 26) {
            mp_raise_ValueError(MP_ERROR_TEXT("Thread channels are 11 to 26"));
        }
    }
    if (args[ARG_panid].u_obj != mp_const_none) {
        panid = mp_obj_get_int(args[ARG_panid].u_obj);
        if (panid < 0 || panid >= 0xffff) {
            mp_raise_ValueError(MP_ERROR_TEXT("a PAN ID is 0 to 0xfffe"));
        }
    }

    otOperationalDataset ds;
    otOperationalDatasetTlvs tlvs;
    otInstance *ot = ot_lock();
    otError err = otDatasetCreateNewNetwork(ot, &ds);
    ot_unlock();
    ot_check(err);
    if (name != NULL) {
        ot_check(otNetworkNameFromString(&ds.mNetworkName, name));
        ds.mComponents.mIsNetworkNamePresent = true;
    }
    if (channel >= 0) {
        ds.mChannel = channel;
        ds.mComponents.mIsChannelPresent = true;
    }
    if (panid >= 0) {
        ds.mPanId = panid;
        ds.mComponents.mIsPanIdPresent = true;
    }
    otDatasetConvertToTlvs(&ds, &tlvs);
    return mp_obj_new_bytes(tlvs.mTlvs, tlvs.mLength);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(ot_dataset_new_obj, 0, ot_dataset_new);

// openthread.dataset() -> bytes or None: the active dataset as TLVs.
// openthread.dataset(tlvs): make *tlvs* the active dataset, saved in flash.
static mp_obj_t ot_dataset(size_t n_args, const mp_obj_t *args) {
    otOperationalDatasetTlvs tlvs;
    if (n_args == 0) {
        otInstance *ot = ot_lock();
        otError err = otDatasetGetActiveTlvs(ot, &tlvs);
        ot_unlock();
        if (err == OT_ERROR_NOT_FOUND) {
            return mp_const_none;
        }
        ot_check(err);
        return mp_obj_new_bytes(tlvs.mTlvs, tlvs.mLength);
    }
    mp_buffer_info_t buf;
    mp_get_buffer_raise(args[0], &buf, MP_BUFFER_READ);
    if (buf.len == 0 || buf.len > OT_OPERATIONAL_DATASET_MAX_LENGTH) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("a dataset is 1 to %d bytes of TLVs"), OT_OPERATIONAL_DATASET_MAX_LENGTH);
    }
    memcpy(tlvs.mTlvs, buf.buf, buf.len);
    tlvs.mLength = buf.len;
    otOperationalDataset parsed;
    ot_check(otDatasetParseTlvs(&tlvs, &parsed));
    if (!parsed.mComponents.mIsNetworkKeyPresent || !parsed.mComponents.mIsChannelPresent || !parsed.mComponents.mIsPanIdPresent) {
        mp_raise_ValueError(MP_ERROR_TEXT("a dataset needs at least a network key, a channel and a PAN ID"));
    }
    otInstance *ot = ot_lock();
    otError err = otDatasetSetActiveTlvs(ot, &tlvs);
    ot_unlock();
    ot_check(err);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(ot_dataset_obj, 0, 1, ot_dataset);

// --- up, role and what the node is ----------------------------------------------

// openthread.up() -> bool: whether the Thread interface is up.
// openthread.up(on): bring it up, which forms the dataset's network or joins
// it, or take it down. Coming up needs a dataset.
static mp_obj_t ot_up(size_t n_args, const mp_obj_t *args) {
    otInstance *ot = ot_lock();
    if (n_args == 0) {
        bool on = otThreadGetDeviceRole(ot) != OT_DEVICE_ROLE_DISABLED;
        ot_unlock();
        return mp_obj_new_bool(on);
    }
    otError err;
    if (mp_obj_is_true(args[0])) {
        if (!otDatasetIsCommissioned(ot)) {
            ot_unlock();
            mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("OpenThread: no dataset; set one with openthread.dataset()"));
        }
        err = otIp6SetEnabled(ot, true);
        if (err == OT_ERROR_NONE) {
            err = otThreadSetEnabled(ot, true);
        }
    } else {
        err = otThreadSetEnabled(ot, false);
        if (err == OT_ERROR_NONE && !s_discovering) {
            err = otIp6SetEnabled(ot, false);
        }
    }
    ot_unlock();
    ot_check(err);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(ot_up_obj, 0, 1, ot_up);

// openthread.role() -> str: "disabled", "detached", "child", "router" or
// "leader". "disabled" too before start().
static mp_obj_t ot_role(void) {
    if (!s_started) {
        return MP_OBJ_NEW_QSTR(MP_QSTR_disabled);
    }
    otInstance *ot = ot_lock();
    const char *role = otThreadDeviceRoleToString(otThreadGetDeviceRole(ot));
    ot_unlock();
    return mp_obj_new_str(role, strlen(role));
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_role_obj, ot_role);

// openthread.info() -> dict: this node and its network, from the stack.
static mp_obj_t ot_info(void) {
    otInstance *ot = ot_lock();
    otNetworkName name;
    strncpy(name.m8, otThreadGetNetworkName(ot), sizeof(name.m8) - 1);
    name.m8[sizeof(name.m8) - 1] = 0;
    otExtendedPanId extpanid = *otThreadGetExtendedPanId(ot);
    otExtAddress extaddr = *otLinkGetExtendedAddress(ot);
    otIp6Address mleid = *otThreadGetMeshLocalEid(ot);
    uint8_t channel = otLinkGetChannel(ot);
    otPanId panid = otLinkGetPanId(ot);
    uint16_t rloc16 = otThreadGetRloc16(ot);
    otDeviceRole role = otThreadGetDeviceRole(ot);
    uint32_t partition = otThreadGetPartitionId(ot);
    const char *role_str = otThreadDeviceRoleToString(role);
    ot_unlock();

    mp_obj_t d = mp_obj_new_dict(9);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_role), mp_obj_new_str(role_str, strlen(role_str)));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_name), mp_obj_new_str(name.m8, strlen(name.m8)));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_channel), MP_OBJ_NEW_SMALL_INT(channel));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_panid), MP_OBJ_NEW_SMALL_INT(panid));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_extpanid), ot_hex(extpanid.m8, OT_EXT_PAN_ID_SIZE));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_extaddr), ot_hex(extaddr.m8, OT_EXT_ADDRESS_SIZE));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_rloc16), MP_OBJ_NEW_SMALL_INT(rloc16));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_mleid), ot_addr_str(&mleid));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_partition), mp_obj_new_int_from_uint(partition));
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_info_obj, ot_info);

// openthread.addresses() -> list of str: this node's IPv6 addresses on the
// Thread interface.
static mp_obj_t ot_addresses(void) {
    otIp6Address addrs[12];
    size_t n = 0;
    otInstance *ot = ot_lock();
    for (const otNetifAddress *a = otIp6GetUnicastAddresses(ot); a != NULL && n < MP_ARRAY_SIZE(addrs); a = a->mNext) {
        addrs[n++] = a->mAddress;
    }
    ot_unlock();
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (size_t i = 0; i < n; i++) {
        mp_obj_list_append(list, ot_addr_str(&addrs[i]));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_addresses_obj, ot_addresses);

// openthread.neighbors() -> list of (extaddr hex, rloc16, average RSSI,
// is_child): the nodes this one hears directly.
static mp_obj_t ot_neighbors(void) {
    otNeighborInfo info[10];
    size_t n = 0;
    otNeighborInfoIterator it = OT_NEIGHBOR_INFO_ITERATOR_INIT;
    otInstance *ot = ot_lock();
    while (n < MP_ARRAY_SIZE(info) && otThreadGetNextNeighborInfo(ot, &it, &info[n]) == OT_ERROR_NONE) {
        n++;
    }
    ot_unlock();
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (size_t i = 0; i < n; i++) {
        mp_obj_t t[4] = {
            ot_hex(info[i].mExtAddress.m8, OT_EXT_ADDRESS_SIZE),
            MP_OBJ_NEW_SMALL_INT(info[i].mRloc16),
            MP_OBJ_NEW_SMALL_INT(info[i].mAverageRssi),
            mp_obj_new_bool(info[i].mIsChild),
        };
        mp_obj_list_append(list, mp_obj_new_tuple(4, t));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_neighbors_obj, ot_neighbors);

// --- finding networks -------------------------------------------------------------

// Runs in the OpenThread task, which holds the lock while it calls.
static void ot_found_cb(otActiveScanResult *result, void *context) {
    (void)context;
    if (result == NULL) {
        s_discovering = false;
        return;
    }
    for (uint8_t i = 0; i < s_found_count; i++) {
        if (memcmp(s_found[i].extpanid.m8, result->mExtendedPanId.m8, OT_EXT_PAN_ID_SIZE) == 0) {
            if (result->mRssi > s_found[i].rssi) {
                s_found[i].rssi = result->mRssi;
            }
            return;
        }
    }
    if (s_found_count < OT_FOUND_MAX) {
        ot_found_t *f = &s_found[s_found_count++];
        f->name = result->mNetworkName;
        f->extpanid = result->mExtendedPanId;
        f->panid = result->mPanId;
        f->channel = result->mChannel;
        f->rssi = result->mRssi;
    }
}

// openthread.discover(): start looking for Thread networks on every channel,
// for a few seconds. It brings the IPv6 side up, which looking needs, and
// leaves it up.
static mp_obj_t ot_discover(void) {
    otInstance *ot = ot_lock();
    otError err = OT_ERROR_NONE;
    if (!otIp6IsEnabled(ot)) {
        err = otIp6SetEnabled(ot, true);
    }
    if (err == OT_ERROR_NONE) {
        s_found_count = 0;
        err = otThreadDiscover(ot, 0, OT_PANID_BROADCAST, false, false, ot_found_cb, NULL);
        s_discovering = err == OT_ERROR_NONE;
    }
    ot_unlock();
    ot_check(err);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_discover_obj, ot_discover);

// openthread.discovered() -> list or None: None while discover() is still
// looking, then the networks it found as (name, extpanid hex, panid,
// channel, rssi).
static mp_obj_t ot_discovered(void) {
    ot_found_t found[OT_FOUND_MAX];
    otInstance *ot = ot_lock();
    (void)ot;
    bool busy = s_discovering;
    uint8_t n = s_found_count;
    memcpy(found, s_found, sizeof(found));
    ot_unlock();
    if (busy) {
        return mp_const_none;
    }
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (uint8_t i = 0; i < n; i++) {
        mp_obj_t t[5] = {
            mp_obj_new_str(found[i].name.m8, strlen(found[i].name.m8)),
            ot_hex(found[i].extpanid.m8, OT_EXT_PAN_ID_SIZE),
            MP_OBJ_NEW_SMALL_INT(found[i].panid),
            MP_OBJ_NEW_SMALL_INT(found[i].channel),
            MP_OBJ_NEW_SMALL_INT(found[i].rssi),
        };
        mp_obj_list_append(list, mp_obj_new_tuple(5, t));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_discovered_obj, ot_discovered);

// --- UDP ----------------------------------------------------------------------------

// Runs in the OpenThread task, which holds the lock while it calls.
static void ot_udp_cb(void *context, otMessage *msg, const otMessageInfo *info) {
    (void)context;
    if (s_inbox == NULL) {
        return;
    }
    if (s_count == OT_UDP_SLOTS) {
        s_head = (s_head + 1) % OT_UDP_SLOTS;
        s_count--;
        s_dropped++;
    }
    ot_datagram_t *d = &s_inbox[(s_head + s_count) % OT_UDP_SLOTS];
    uint16_t offset = otMessageGetOffset(msg);
    uint16_t len = otMessageGetLength(msg) - offset;
    if (len > OT_UDP_MAX) {
        len = OT_UDP_MAX;
        s_truncated++;
    }
    d->addr = info->mPeerAddr;
    d->port = info->mPeerPort;
    d->len = otMessageRead(msg, offset, d->data, len);
    s_count++;
}

static void ot_udp_close_locked(otInstance *ot) {
    if (s_socket_open) {
        otUdpClose(ot, &s_socket);
        s_socket_open = false;
    }
    s_count = 0;
    s_head = 0;
}

// openthread.udp_open(port): listen for UDP on *port* (and send from it).
// One socket at a time; opening again moves it.
static mp_obj_t ot_udp_open(mp_obj_t port_in) {
    mp_int_t port = mp_obj_get_int(port_in);
    if (port <= 0 || port > 0xffff) {
        mp_raise_ValueError(MP_ERROR_TEXT("a UDP port is 1 to 65535"));
    }
    if (s_inbox == NULL) {
        s_inbox = heap_caps_malloc(OT_UDP_SLOTS * sizeof(ot_datagram_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (s_inbox == NULL) {
            s_inbox = heap_caps_malloc(OT_UDP_SLOTS * sizeof(ot_datagram_t), MALLOC_CAP_8BIT);
        }
        if (s_inbox == NULL) {
            mp_raise_type(&mp_type_MemoryError);
        }
    }
    otInstance *ot = ot_lock();
    ot_udp_close_locked(ot);
    otSockAddr name;
    memset(&name, 0, sizeof(name));
    name.mPort = port;
    otError err = otUdpOpen(ot, &s_socket, ot_udp_cb, NULL);
    if (err == OT_ERROR_NONE) {
        s_socket_open = true;
        err = otUdpBind(ot, &s_socket, &name, OT_NETIF_THREAD_INTERNAL);
        if (err != OT_ERROR_NONE) {
            ot_udp_close_locked(ot);
        }
    }
    ot_unlock();
    ot_check(err);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(ot_udp_open_obj, ot_udp_open);

// openthread.udp_close()
static mp_obj_t ot_udp_close(void) {
    if (s_started) {
        otInstance *ot = ot_lock();
        ot_udp_close_locked(ot);
        ot_unlock();
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_udp_close_obj, ot_udp_close);

// openthread.udp_send(addr, port, data): send *data* to IPv6 *addr*, which
// may be a multicast address such as "ff03::1" (every node on the network).
static mp_obj_t ot_udp_send(mp_obj_t addr_in, mp_obj_t port_in, mp_obj_t data_in) {
    const char *addr = mp_obj_str_get_str(addr_in);
    mp_int_t port = mp_obj_get_int(port_in);
    mp_buffer_info_t buf;
    mp_get_buffer_raise(data_in, &buf, MP_BUFFER_READ);
    if (port <= 0 || port > 0xffff) {
        mp_raise_ValueError(MP_ERROR_TEXT("a UDP port is 1 to 65535"));
    }
    if (buf.len > 1024) {
        mp_raise_ValueError(MP_ERROR_TEXT("a Thread UDP datagram is 1024 bytes at most"));
    }
    otMessageInfo info;
    memset(&info, 0, sizeof(info));
    if (otIp6AddressFromString(addr, &info.mPeerAddr) != OT_ERROR_NONE) {
        mp_raise_ValueError(MP_ERROR_TEXT("not an IPv6 address"));
    }
    info.mPeerPort = port;
    otInstance *ot = ot_lock();
    otError err = OT_ERROR_INVALID_STATE;
    if (s_socket_open) {
        otMessage *msg = otUdpNewMessage(ot, NULL);
        err = msg == NULL ? OT_ERROR_NO_BUFS : otMessageAppend(msg, buf.buf, buf.len);
        if (err == OT_ERROR_NONE) {
            err = otUdpSend(ot, &s_socket, msg, &info);
        }
        if (err != OT_ERROR_NONE && msg != NULL) {
            otMessageFree(msg);
        }
    }
    ot_unlock();
    if (!s_socket_open) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("OpenThread: call openthread.udp_open(port) first"));
    }
    ot_check(err);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(ot_udp_send_obj, ot_udp_send);

// openthread.udp_recv() -> (addr, port, bytes) or None: the oldest datagram
// that arrived, without waiting.
static mp_obj_t ot_udp_recv(void) {
    if (!s_started || s_inbox == NULL) {
        return mp_const_none;
    }
    otIp6Address addr;
    uint16_t port = 0, len = 0;
    uint8_t data[OT_UDP_MAX];
    bool got = false;
    otInstance *ot = ot_lock();
    (void)ot;
    if (s_count) {
        ot_datagram_t *d = &s_inbox[s_head];
        addr = d->addr;
        port = d->port;
        len = d->len;
        memcpy(data, d->data, len);
        s_head = (s_head + 1) % OT_UDP_SLOTS;
        s_count--;
        got = true;
    }
    ot_unlock();
    if (!got) {
        return mp_const_none;
    }
    mp_obj_t t[3] = { ot_addr_str(&addr), MP_OBJ_NEW_SMALL_INT(port), mp_obj_new_bytes(data, len) };
    return mp_obj_new_tuple(3, t);
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_udp_recv_obj, ot_udp_recv);

// openthread.counts() -> (dropped, truncated): datagrams lost because the
// queue was full, and cut to 256 bytes.
static mp_obj_t ot_counts(void) {
    mp_obj_t t[2] = { mp_obj_new_int_from_uint(s_dropped), mp_obj_new_int_from_uint(s_truncated) };
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_0(ot_counts_obj, ot_counts);

// openthread.__revision__: which openthread module this firmware was built
// from. The build computes it from this repo's own git.
#ifndef OPENTHREAD_REVISION
#define OPENTHREAD_REVISION "unknown"
#endif
static MP_DEFINE_STR_OBJ(ot_revision_obj, OPENTHREAD_REVISION);

static const mp_rom_map_elem_t ot_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_openthread) },
    { MP_ROM_QSTR(MP_QSTR___revision__), MP_ROM_PTR(&ot_revision_obj) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&ot_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&ot_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_dataset_new), MP_ROM_PTR(&ot_dataset_new_obj) },
    { MP_ROM_QSTR(MP_QSTR_dataset), MP_ROM_PTR(&ot_dataset_obj) },
    { MP_ROM_QSTR(MP_QSTR_up), MP_ROM_PTR(&ot_up_obj) },
    { MP_ROM_QSTR(MP_QSTR_role), MP_ROM_PTR(&ot_role_obj) },
    { MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&ot_info_obj) },
    { MP_ROM_QSTR(MP_QSTR_addresses), MP_ROM_PTR(&ot_addresses_obj) },
    { MP_ROM_QSTR(MP_QSTR_neighbors), MP_ROM_PTR(&ot_neighbors_obj) },
    { MP_ROM_QSTR(MP_QSTR_discover), MP_ROM_PTR(&ot_discover_obj) },
    { MP_ROM_QSTR(MP_QSTR_discovered), MP_ROM_PTR(&ot_discovered_obj) },
    { MP_ROM_QSTR(MP_QSTR_udp_open), MP_ROM_PTR(&ot_udp_open_obj) },
    { MP_ROM_QSTR(MP_QSTR_udp_close), MP_ROM_PTR(&ot_udp_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_udp_send), MP_ROM_PTR(&ot_udp_send_obj) },
    { MP_ROM_QSTR(MP_QSTR_udp_recv), MP_ROM_PTR(&ot_udp_recv_obj) },
    { MP_ROM_QSTR(MP_QSTR_counts), MP_ROM_PTR(&ot_counts_obj) },
};
static MP_DEFINE_CONST_DICT(ot_module_globals, ot_module_globals_table);

const mp_obj_module_t openthread_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&ot_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_openthread, openthread_user_cmodule);

#endif // CONFIG_OPENTHREAD_ENABLED
