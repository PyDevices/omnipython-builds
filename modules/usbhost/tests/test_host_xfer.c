// SPDX-License-Identifier: MIT
//
// Host-side tests for usb.core's bulk and interrupt transfers
// (src/usbhost_host_xfer.c), against a fake of ESP-IDF's host library in
// tests/host_xfer/. The fake device lands a packet in an armed IN transfer at
// a set time, and the host library reports it a little later, as its task
// gets round to it. A transfer that is halted and flushed before then is
// reported empty, as IDF's controller driver does: the packet is gone.
//
// Built with -DUSBHOST_XFER_PLANT_RETIRE_IN, a read that raises on its
// timeout retires its transfer the old way, and this test has to fail (CI
// checks that it does).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "usb/usb_host.h"
#include "py/mperrno.h"

int usbhost_xfer_claim(uint32_t dev_id, uint8_t itf, uint8_t alt);
int usbhost_xfer_ep(uint32_t dev_id, uint8_t ep, uint8_t *data, size_t len, uint32_t timeout_ms, bool keep);
int usbhost_xfer_poll(uint32_t dev_id, uint8_t ep, uint8_t *data, size_t len);

static int failures = 0;

#define CHECK(cond) do { \
    if (!(cond)) { \
        printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        failures++; \
    } \
} while (0)

// -- the fake clock and RTOS

static int64_t now_us;

struct fake_sem {
    int count;
};

static void fake_bus(void);

int64_t esp_timer_get_time(void) {
    return now_us;
}

void esp_rom_delay_us(uint32_t us) {
    now_us += us;
    fake_bus();
}

SemaphoreHandle_t xSemaphoreCreateBinary(void) {
    return calloc(1, sizeof(struct fake_sem));
}

BaseType_t xSemaphoreGive(SemaphoreHandle_t sem) {
    sem->count = 1;
    return pdTRUE;
}

void vSemaphoreDelete(SemaphoreHandle_t sem) {
    free(sem);
}

// The host task runs once a tick while the caller sleeps.
BaseType_t xSemaphoreTake(SemaphoreHandle_t sem, TickType_t ticks) {
    for (TickType_t t = 0;; t++) {
        if (sem->count) {
            sem->count = 0;
            return pdTRUE;
        }
        if (t >= ticks || t > 100000) {
            return pdFALSE;
        }
        now_us += 1000;
        fake_bus();
        usb_host_client_handle_events(NULL, 0);
    }
}

void vTaskDelay(TickType_t ticks) {
    now_us += (int64_t)ticks * 1000;
    fake_bus();
}

// -- the rest of usbhost_host.c, as usbhost_host_xfer.c sees it

static struct fake_dev {
    int unused;
} the_dev;

int usbhost_host_dev_lookup(uint32_t dev_id, usb_device_handle_t *out) {
    if (dev_id != 1) {
        return -1;
    }
    *out = &the_dev;
    return 0;
}

usb_host_client_handle_t usbhost_host_client_get(void) {
    return NULL;
}

void usbhost_host_fifo_limits(uint32_t *in_bytes, uint32_t *ptx_bytes) {
    *in_bytes = *ptx_bytes = 0;
}

void usbhost_host_lock(void) {
}

void usbhost_host_unlock(void) {
}

int usbhost_host_lock_suspend(void) {
    return 0;
}

void usbhost_host_lock_resume(int held) {
    (void)held;
}

void usbhost_host_ctrl_abandon(usb_transfer_t *xfer) {
    (void)xfer;
}

bool usbhost_host_ctrl_reclaim(usb_transfer_t *xfer) {
    (void)xfer;
    return false;
}

esp_err_t usbhost_host_in_transfer_alloc(size_t size, int num_isoc_packets, usb_transfer_t **out) {
    return usb_host_transfer_alloc(size, num_isoc_packets, out);
}

void usbhost_stream_stop_itf(void *dev, int itf, bool device_gone) {
    (void)dev;
    (void)itf;
    (void)device_gone;
}

// -- the fake host library and device: one bulk IN (0x81) and one bulk OUT
// (0x02) endpoint, 64-byte packets, on interface 0.

static const uint8_t config_desc[] = {
    9, 2, 32, 0, 1, 1, 0, 0x80, 50,
    9, 4, 0, 0, 2, 0xFF, 0, 0, 0,
    7, 5, 0x81, 2, 64, 0, 0,
    7, 5, 0x02, 2, 64, 0, 0,
};

#define DELIVER_LAG_US (1000)   // how long the library takes to report a finished transfer

static struct {
    // the device's next IN packet
    bool queued;
    int64_t at_us;
    uint8_t data[64];
    int len;
    // the armed IN transfer, and what has landed in it
    usb_transfer_t *in_xfer;
    bool landed;
    int64_t landed_us;
    int landed_len;
    bool in_flushed;
    // the OUT transfer; the device never takes it when out_stuck
    usb_transfer_t *out_xfer;
    bool out_stuck;
    bool out_flushed;
    int submits, halts;
} bus;

static void fake_reset(void) {
    memset(&bus, 0, sizeof(bus));
}

static void device_sends(int64_t at_us, const uint8_t *data, int len) {
    bus.queued = true;
    bus.at_us = at_us;
    memcpy(bus.data, data, (size_t)len);
    bus.len = len;
}

static void fake_bus(void) {
    if (bus.in_xfer != NULL && !bus.landed && !bus.in_flushed && bus.queued && now_us >= bus.at_us) {
        memcpy(bus.in_xfer->data_buffer, bus.data, (size_t)bus.len);
        bus.landed = true;
        bus.landed_us = now_us;
        bus.landed_len = bus.len;
        bus.queued = false;
    }
}

static void complete(usb_transfer_t **slot, usb_transfer_status_t status, int actual) {
    usb_transfer_t *x = *slot;
    *slot = NULL;
    x->status = status;
    x->actual_num_bytes = actual;
    x->callback(x);
}

esp_err_t usb_host_client_handle_events(usb_host_client_handle_t client, uint32_t ticks) {
    (void)client;
    (void)ticks;
    fake_bus();
    if (bus.in_xfer != NULL) {
        if (bus.in_flushed) {
            bus.in_flushed = false;
            bus.landed = false;
            complete(&bus.in_xfer, USB_TRANSFER_STATUS_CANCELED, 0);   // IDF's HCD: a halted transfer is empty
        } else if (bus.landed && now_us >= bus.landed_us + DELIVER_LAG_US) {
            bus.landed = false;
            complete(&bus.in_xfer, USB_TRANSFER_STATUS_COMPLETED, bus.landed_len);
        }
    }
    if (bus.out_xfer != NULL) {
        if (bus.out_flushed) {
            bus.out_flushed = false;
            complete(&bus.out_xfer, USB_TRANSFER_STATUS_CANCELED, 0);
        } else if (!bus.out_stuck) {
            complete(&bus.out_xfer, USB_TRANSFER_STATUS_COMPLETED, bus.out_xfer->num_bytes);
        }
    }
    return ESP_OK;
}

esp_err_t usb_host_device_info(usb_device_handle_t dev, usb_device_info_t *info) {
    (void)dev;
    info->speed = USB_SPEED_HIGH;
    return ESP_OK;
}

esp_err_t usb_host_get_active_config_descriptor(usb_device_handle_t dev, const usb_config_desc_t **cfg) {
    (void)dev;
    *cfg = (const usb_config_desc_t *)config_desc;
    return ESP_OK;
}

esp_err_t usb_host_interface_claim(usb_host_client_handle_t client, usb_device_handle_t dev, uint8_t itf, uint8_t alt) {
    (void)client;
    (void)dev;
    return itf == 0 && alt == 0 ? ESP_OK : ESP_ERR_NOT_FOUND;
}

esp_err_t usb_host_interface_release(usb_host_client_handle_t client, usb_device_handle_t dev, uint8_t itf) {
    (void)client;
    (void)dev;
    (void)itf;
    return ESP_OK;
}

esp_err_t usb_host_transfer_alloc(size_t size, int num_isoc_packets, usb_transfer_t **out) {
    (void)num_isoc_packets;
    usb_transfer_t *x = calloc(1, sizeof(*x));
    x->data_buffer = calloc(1, size);
    x->data_buffer_size = size;
    *out = x;
    return ESP_OK;
}

esp_err_t usb_host_transfer_free(usb_transfer_t *x) {
    free(x->data_buffer);
    free(x);
    return ESP_OK;
}

esp_err_t usb_host_transfer_submit(usb_transfer_t *x) {
    bus.submits++;
    if (x->bEndpointAddress & 0x80) {
        CHECK(bus.in_xfer == NULL);     // never two on one endpoint
        bus.in_xfer = x;
    } else {
        CHECK(bus.out_xfer == NULL);
        bus.out_xfer = x;
    }
    fake_bus();
    return ESP_OK;
}

esp_err_t usb_host_transfer_submit_control(usb_host_client_handle_t client, usb_transfer_t *x) {
    (void)client;
    (void)x;
    return ESP_FAIL;
}

esp_err_t usb_host_endpoint_halt(usb_device_handle_t dev, uint8_t ep) {
    (void)dev;
    (void)ep;
    bus.halts++;
    return ESP_OK;
}

esp_err_t usb_host_endpoint_flush(usb_device_handle_t dev, uint8_t ep) {
    (void)dev;
    if (ep & 0x80) {
        bus.in_flushed = bus.in_xfer != NULL;
    } else {
        bus.out_flushed = bus.out_xfer != NULL;
    }
    return ESP_OK;
}

esp_err_t usb_host_endpoint_clear(usb_device_handle_t dev, uint8_t ep) {
    (void)dev;
    (void)ep;
    return ESP_OK;
}

// -- the tests

static uint8_t packet[64];

static void a_packet_landing_as_a_raising_read_times_out_is_kept(void) {
    fake_reset();
    // It lands at 4.5 ms; the library would report it at 5.5 ms; the read
    // gives up at 5 ms.
    device_sends(now_us + 4500, packet, 64);
    uint8_t buf[64] = {0};
    CHECK(usbhost_xfer_ep(1, 0x81, buf, 64, 5, false) == -MP_ETIMEDOUT);
    CHECK(bus.halts == 0);
    int r = usbhost_xfer_ep(1, 0x81, buf, 64, 100, false);
    CHECK(r == 64);
    CHECK(memcmp(buf, packet, 64) == 0);
    CHECK(bus.submits == 1);    // collected, not submitted again
}

static void the_default_reads_quarter_second_steps_lose_nothing(void) {
    fake_reset();
    // usb.core's read with no timeout: 250 ms steps, each a raising read.
    // Here the steps are 5 ms, with the packet landing across the second.
    device_sends(now_us + 9500, packet, 64);
    uint8_t buf[64] = {0};
    int r, steps = 0;
    while ((r = usbhost_xfer_ep(1, 0x81, buf, 64, 5, false)) == -MP_ETIMEDOUT && steps < 10) {
        steps++;
    }
    CHECK(steps == 2);
    CHECK(r == 64);
    CHECK(memcmp(buf, packet, 64) == 0);
}

static void a_zero_length_packet_is_0_and_a_timeout_is_not(void) {
    fake_reset();
    uint8_t buf[64];
    CHECK(usbhost_xfer_ep(1, 0x81, buf, 64, 3, false) == -MP_ETIMEDOUT);
    device_sends(now_us + 500, packet, 0);
    CHECK(usbhost_xfer_ep(1, 0x81, buf, 64, 20, false) == 0);
    // A kept poll says 0 for both.
    CHECK(usbhost_xfer_ep(1, 0x81, buf, 64, 3, true) == 0);
    device_sends(now_us + 500, packet, 0);
    CHECK(usbhost_xfer_ep(1, 0x81, buf, 64, 20, true) == 0);
    CHECK(bus.submits == 2);
}

static void bytes_beyond_a_short_read_wait_for_the_next(void) {
    fake_reset();
    device_sends(now_us + 100, packet, 64);
    uint8_t buf[64] = {0};
    CHECK(usbhost_xfer_ep(1, 0x81, buf, 10, 50, false) == 10);
    CHECK(memcmp(buf, packet, 10) == 0);
    memset(buf, 0, sizeof(buf));
    CHECK(usbhost_xfer_ep(1, 0x81, buf, 64, 50, false) == 54);
    CHECK(memcmp(buf, packet + 10, 54) == 0);
    CHECK(bus.submits == 1);
    CHECK(usbhost_xfer_poll(1, 0x81, buf, 64) == 0);   // all taken: the next read arms a transfer
    CHECK(bus.submits == 2);
}

static void an_out_transfer_that_times_out_is_retired(void) {
    fake_reset();
    // The IN transfer the last test left armed belongs to a pipe of its own.
    bus.out_stuck = true;
    uint8_t data[31] = {1};
    CHECK(usbhost_xfer_ep(1, 0x02, data, sizeof(data), 5, false) == -MP_ETIMEDOUT);
    CHECK(bus.halts == 1);
    CHECK(bus.out_xfer == NULL);
    bus.out_stuck = false;
    CHECK(usbhost_xfer_ep(1, 0x02, data, sizeof(data), 5, false) == (int)sizeof(data));
}

int main(void) {
    for (int i = 0; i < 64; i++) {
        packet[i] = (uint8_t)(i * 7 + 3);
    }
    CHECK(usbhost_xfer_claim(1, 0, 0) == 1);
    a_packet_landing_as_a_raising_read_times_out_is_kept();
    the_default_reads_quarter_second_steps_lose_nothing();
    a_zero_length_packet_is_0_and_a_timeout_is_not();
    bytes_beyond_a_short_read_wait_for_the_next();
    an_out_transfer_that_times_out_is_retired();
    if (failures) {
        printf("%d FAILED\n", failures);
        return 1;
    }
    printf("test_host_xfer: all passed\n");
    return 0;
}
