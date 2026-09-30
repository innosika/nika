set(SOURCES
    "SpaceKnowledgeModule.cpp"
    "agent/SpaceKnowledgeInferenceAgent.cpp"
)

set(HEADERS
    "SpaceKnowledgeModule.hpp"
    "keynodes/SpaceKnowledgeKeynodes.hpp"
    "agent/SpaceKnowledgeInferenceAgent.hpp"
)

add_library(space-knowledge-module SHARED ${SOURCES} ${HEADERS})
target_link_libraries(space-knowledge-module
    LINK_PUBLIC sc-machine::sc-config
    LINK_PUBLIC scl-machine::inference
    LINK_PUBLIC common
)
target_include_directories(space-knowledge-module
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}
)
set_target_properties(space-knowledge-module PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${SC_EXTENSIONS_DIRECTORY})

if(${SC_CLANG_FORMAT_CODE})
    target_clangformat_setup(space-knowledge-module)
endif()
