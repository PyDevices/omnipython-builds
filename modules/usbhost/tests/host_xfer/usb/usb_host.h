// SPDX-License-Identifier: MIT
//
// The part of ESP-IDF's USB host library that usbhost_host_xfer.c calls, for
// the host tests. test_host_xfer.c implements it as a fake bus and device.
#ifndef FAKE_USB_HOST_H
#define FAKE_USB_HOST_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef int esp_err_t;
#define ESP_OK (0)
#define ESP_FAIL (-1)
#define ESP_ERR_NO_MEM (0x101)
#define ESP_ERR_NOT_FOUND (0x105)
#define ESP_ERR_NOT_SUPPORTED (0x106)

typedef struct fake_dev *usb_device_handle_t;
typedef struct fake_client *usb_host_client_handle_t;

typedef enum {
    USB_TRANSFER_STATUS_COMPLETED,
    USB_TRANSFER_STATUS_ERROR,
    USB_TRANSFER_STATUS_TIMED_OUT,
    USB_TRANSFER_STATUS_CANCELED,
    USB_TRANSFER_STATUS_STALL,
    USB_TRANSFER_STATUS_OVERFLOW,
    USB_TRANSFER_STATUS_SKIPPED,
    USB_TRANSFER_STATUS_NO_DEVICE,
} usb_transfer_status_t;

typedef enum { USB_SPEED_LOW, USB_SPEED_FULL, USB_SPEED_HIGH } usb_speed_t;

typedef struct usb_transfer_s usb_transfer_t;
typedef void (*usb_transfer_cb_t)(usb_transfer_t *transfer);
struct usb_transfer_s {
    uint8_t *data_buffer;
    size_t data_buffer_size;
    int num_bytes;
    int actual_num_bytes;
    uint32_t flags;
    usb_device_handle_t device_handle;
    uint8_t bEndpointAddress;
    usb_transfer_status_t status;
    uint32_t timeout_ms;
    usb_transfer_cb_t callback;
    void *context;
};

typedef struct {
    uint8_t bLength;
    uint8_t bDescriptorType;
    uint16_t wTotalLength;
} __attribute__((packed)) usb_config_desc_t;

typedef struct {
    usb_speed_t speed;
} usb_device_info_t;

typedef struct {
    uint8_t raw[8];
} usb_setup_packet_t;

#define USB_B_DESCRIPTOR_TYPE_INTERFACE (0x04)
#define USB_B_DESCRIPTOR_TYPE_ENDPOINT (0x05)

esp_err_t usb_host_device_info(usb_device_handle_t dev, usb_device_info_t *info);
esp_err_t usb_host_get_active_config_descriptor(usb_device_handle_t dev, const usb_config_desc_t **cfg);
esp_err_t usb_host_interface_claim(usb_host_client_handle_t client, usb_device_handle_t dev, uint8_t itf, uint8_t alt);
esp_err_t usb_host_interface_release(usb_host_client_handle_t client, usb_device_handle_t dev, uint8_t itf);
esp_err_t usb_host_transfer_alloc(size_t size, int num_isoc_packets, usb_transfer_t **out);
esp_err_t usb_host_transfer_free(usb_transfer_t *x);
esp_err_t usb_host_transfer_submit(usb_transfer_t *x);
esp_err_t usb_host_transfer_submit_control(usb_host_client_handle_t client, usb_transfer_t *x);
esp_err_t usb_host_endpoint_halt(usb_device_handle_t dev, uint8_t ep);
esp_err_t usb_host_endpoint_flush(usb_device_handle_t dev, uint8_t ep);
esp_err_t usb_host_endpoint_clear(usb_device_handle_t dev, uint8_t ep);
esp_err_t usb_host_client_handle_events(usb_host_client_handle_t client, uint32_t ticks);
#endif
