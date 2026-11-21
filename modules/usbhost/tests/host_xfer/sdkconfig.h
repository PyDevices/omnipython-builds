// SPDX-License-Identifier: MIT
//
// A stand-in for the IDF's sdkconfig.h, so usbhost_host_xfer.c compiles on a
// desktop against the fake host library in this folder.
#define CONFIG_SOC_USB_OTG_SUPPORTED 1
