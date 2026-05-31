cmake_minimum_required(VERSION 3.20)

project(ProjectZomboidCppEngine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenGL REQUIRED)
find_package(glfw3 CONFIG QUIET)
find_package(glm CONFIG QUIET)

add_executable(pz_engine main.cpp)

target_compile_features(pz_engine PRIVATE cxx_std_20)

if (MSVC)
    target_compile_options(pz_engine PRIVATE /W4 /permissive-)
else()
    target_compile_options(pz_engine PRIVATE -Wall -Wextra -Wpedantic)
endif()

if (TARGET glfw)
    target_link_libraries(pz_engine PRIVATE glfw)
elseif (TARGET glfw3)
    target_link_libraries(pz_engine PRIVATE glfw3)
elseif (TARGET glfw3::glfw)
    target_link_libraries(pz_engine PRIVATE glfw3::glfw)
else()
    message(FATAL_ERROR "GLFW was not found. Install GLFW development files or provide glfw3_DIR.")
endif()

if (TARGET glm::glm)
    target_link_libraries(pz_engine PRIVATE glm::glm)
endif()

target_link_libraries(pz_engine PRIVATE OpenGL::GL)
