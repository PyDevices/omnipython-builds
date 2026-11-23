# openthread CMake glue: a Thread node on ESP-IDF's OpenThread, on the
# ESP32-S31's own 802.15.4 radio. sdkconfig.esp32s31 turns the radio and
# OpenThread on (build_mp.py appends it; on a stock build, add it to your
# board's SDKCONFIG_DEFAULTS). Every other chip and port skips the module.
# --- which openthread this firmware was built from ----------------------
# Computed at build time from this repo's own git, never stored; "unknown" when
# there is no git (a tarball). Read on a target as <module>.__revision__.
execute_process(
    COMMAND git -C ${CMAKE_CURRENT_LIST_DIR} describe --always --dirty --abbrev=7
    OUTPUT_VARIABLE OPENTHREAD_REVISION
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET)
if(NOT OPENTHREAD_REVISION)
    set(OPENTHREAD_REVISION "unknown")
endif()

if(ESP_PLATFORM AND IDF_TARGET STREQUAL "esp32s31")
    add_library(usermod_openthread INTERFACE)
    target_compile_definitions(usermod_openthread INTERFACE OPENTHREAD_REVISION=\"${OPENTHREAD_REVISION}\")
    target_sources(usermod_openthread INTERFACE ${CMAKE_CURRENT_LIST_DIR}/src/mod_openthread.c)
    target_link_libraries(usermod_openthread INTERFACE idf::openthread idf::vfs)
    target_link_libraries(usermod INTERFACE usermod_openthread)
endif()
