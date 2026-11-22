/* Arduino GIGA R1 WiFi with the GIGA Display Shield: the Wi-Fi chip's firmware
   and LVGL's font bitmaps in the QSPI flash the board reserves for the Wi-Fi
   firmware, read in place.
   Linked after the board's own stm32h747.ld. */

MEMORY
{
    FLASH_CYW43 (r) : ORIGIN = 0x90F00000, LENGTH = 1024K
}

SECTIONS
{
    .cyw43_fw :
    {
        . = ALIGN(4);
        KEEP(*(.cyw43_fw*))
        . = ALIGN(4);
    } > FLASH_CYW43

    /* LVGL's font bitmaps, after the Wi-Fi firmware. */
    .qspi_rodata :
    {
        . = ALIGN(4);
        KEEP(*(.qspi_rodata*))
        . = ALIGN(4);
    } > FLASH_CYW43
}
