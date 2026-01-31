cmake_minimum_required(VERSION 3.10)
project(ZoomMeetingBot VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

# システムのQt5を探す
find_package(Qt5 COMPONENTS Core Widgets REQUIRED)

# SDK paths
if(NOT DEFINED ZOOM_SDK_DIR)
    set(ZOOM_SDK_DIR "${CMAKE_SOURCE_DIR}/../../zoom-meeting-sdk-linux_x86_64-6.7.2.7020")
endif()
set(ZOOM_SDK_HEADERS "${ZOOM_SDK_DIR}/h")
set(ZOOM_SDK_LIB "${ZOOM_SDK_DIR}")
set(ZOOM_QT_LIB "${ZOOM_SDK_DIR}/qt_libs/Qt/lib")

# SDK同梱のQtが存在するかチェック
if(EXISTS "${ZOOM_QT_LIB}/libQt5Widgets.so.5")
    set(USE_SDK_QT TRUE)
    message(STATUS "Using SDK Qt libraries from ${ZOOM_QT_LIB}")
else()
    set(USE_SDK_QT FALSE)
    message(STATUS "SDK Qt not found, using system Qt libraries")
endif()

# Find CURL
find_package(CURL REQUIRED)

# Source files
set(SOURCES
    main.cpp
    zoom_meeting_bot.cpp
    audio_raw_data_delegate.cpp
)

# Executable
add_executable(${PROJECT_NAME} ${SOURCES})

# -fPIC for Qt
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC")

# Include directories
target_include_directories(${PROJECT_NAME} PRIVATE
    ${ZOOM_SDK_HEADERS}
    ${ZOOM_SDK_HEADERS}/meeting_service_components
    ${ZOOM_SDK_HEADERS}/rawdata
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${Qt5Core_INCLUDE_DIRS}
    ${Qt5Widgets_INCLUDE_DIRS}
    ${CURL_INCLUDE_DIRS}
)

# Link libraries
if(USE_SDK_QT)
    # SDK同梱のQtライブラリを使用 (x86_64)
    target_link_libraries(${PROJECT_NAME} PRIVATE
        ${ZOOM_SDK_LIB}/libmeetingsdk.so
        pthread
        dl
        X11
        xcb
        Xfixes
        xcb-xtest
        GL
        gbm
        ${ZOOM_QT_LIB}/libQt5Widgets.so.5
        ${ZOOM_QT_LIB}/libQt5Gui.so.5
        ${ZOOM_QT_LIB}/libQt5Core.so.5
        ${ZOOM_QT_LIB}/libQt5Network.so.5
        ${CURL_LIBRARIES}
    )
    set_target_properties(${PROJECT_NAME} PROPERTIES
        BUILD_RPATH "${ZOOM_QT_LIB}:${ZOOM_SDK_LIB}"
        INSTALL_RPATH "${ZOOM_QT_LIB}:${ZOOM_SDK_LIB}"
    )
else()
    # システムのQtライブラリを使用 (arm64)
    target_link_libraries(${PROJECT_NAME} PRIVATE
        ${ZOOM_SDK_LIB}/libmeetingsdk.so
        pthread
        dl
        X11
        xcb
        Xfixes
        xcb-xtest
        GL
        gbm
        Qt5::Core
        Qt5::Widgets
        ${CURL_LIBRARIES}
    )
    set_target_properties(${PROJECT_NAME} PROPERTIES
        BUILD_RPATH "${ZOOM_SDK_LIB}"
        INSTALL_RPATH "${ZOOM_SDK_LIB}"
    )
endif()

# Copy required files to build directory
add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E create_symlink
        ${ZOOM_SDK_LIB}/libmeetingsdk.so
        $<TARGET_FILE_DIR:${PROJECT_NAME}>/libmeetingsdk.so
    COMMENT "Creating symlink to SDK library"
)

