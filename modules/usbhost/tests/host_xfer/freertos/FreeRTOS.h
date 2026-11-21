// SPDX-License-Identifier: MIT
//
// FreeRTOS, as far as usbhost_host_xfer.c uses it, for the host tests. The
// test supplies the functions: time is a fake clock in 1 ms ticks.
#ifndef FAKE_FREERTOS_H
#define FAKE_FREERTOS_H
#include <stdbool.h>
#include <stdint.h>
typedef uint32_t TickType_t;
typedef int BaseType_t;
#define pdTRUE (1)
#define pdFALSE (0)
#define portMAX_DELAY ((TickType_t)0xFFFFFFFF)
#define portTICK_PERIOD_MS (1)
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
typedef struct fake_sem *SemaphoreHandle_t;
typedef void *TaskHandle_t;
SemaphoreHandle_t xSemaphoreCreateBinary(void);
BaseType_t xSemaphoreTake(SemaphoreHandle_t sem, TickType_t ticks);
BaseType_t xSemaphoreGive(SemaphoreHandle_t sem);
void vSemaphoreDelete(SemaphoreHandle_t sem);
void vTaskDelay(TickType_t ticks);
#endif
