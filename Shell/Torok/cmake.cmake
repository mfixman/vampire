target_sources(common PRIVATE
  Shell/Torok/Graph.cpp
  Shell/Torok/Guidance.cpp
  Shell/Torok/Passive.cpp)
add_library(torok_model STATIC Shell/Torok/Model.cpp)
find_package(Torch REQUIRED)
target_link_libraries(torok_model PUBLIC ${TORCH_LIBRARIES})
if(GCC_OR_CLANG)
  target_compile_options(torok_model PRIVATE -frtti)
endif()
separate_arguments(TOROK_TORCH_FLAGS NATIVE_COMMAND "${TORCH_CXX_FLAGS}")
target_compile_options(common PRIVATE ${TOROK_TORCH_FLAGS})
target_compile_options(torok_model PRIVATE ${TOROK_TORCH_FLAGS})
add_compile_options(${TOROK_TORCH_FLAGS})
link_libraries(torok_model)
add_executable(torok_check EXCLUDE_FROM_ALL Shell/Torok/check.cpp $<TARGET_OBJECTS:common>)
