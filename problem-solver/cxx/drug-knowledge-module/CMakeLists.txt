set(SOURCES
    "DrugKnowledgeModule.cpp"
    "agent/DrugKnowledgeInferenceAgent.cpp"
)

set(HEADERS
    "DrugKnowledgeModule.hpp"
    "keynodes/DrugKnowledgeKeynodes.hpp"
    "agent/DrugKnowledgeInferenceAgent.hpp"
)

add_library(drug-knowledge-module SHARED ${SOURCES} ${HEADERS})
target_link_libraries(drug-knowledge-module
    LINK_PUBLIC sc-machine::sc-config
    LINK_PUBLIC scl-machine::inference
    LINK_PUBLIC common
)
target_include_directories(drug-knowledge-module
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}
)
set_target_properties(drug-knowledge-module PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${SC_EXTENSIONS_DIRECTORY})

if(${SC_CLANG_FORMAT_CODE})
    target_clangformat_setup(drug-knowledge-module)
endif()
