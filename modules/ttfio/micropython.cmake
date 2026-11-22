# ttfio CMake glue (see micropython.mk).
set(TTFIO_DIR ${CMAKE_CURRENT_LIST_DIR}/src)

# --- which ttfio this firmware was built from ---------------------------
# Computed at build time from this repo's own git, never stored; "unknown" when
# there is no git (a tarball). Read on a target as <module>.__revision__.
execute_process(
    COMMAND git -C ${CMAKE_CURRENT_LIST_DIR} describe --always --dirty --abbrev=7
    OUTPUT_VARIABLE TTFIO_REVISION
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET)
if(NOT TTFIO_REVISION)
    set(TTFIO_REVISION "unknown")
endif()

add_library(usermod_ttfio INTERFACE)
target_compile_definitions(usermod_ttfio INTERFACE TTFIO_REVISION=\"${TTFIO_REVISION}\")
target_include_directories(usermod_ttfio INTERFACE
    ${TTFIO_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/third_party/stb_truetype
)
target_sources(usermod_ttfio INTERFACE
    ${TTFIO_DIR}/mod_ttfio.c
    ${TTFIO_DIR}/ttfio_core.c
)
target_link_libraries(usermod INTERFACE usermod_ttfio)
