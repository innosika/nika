#include "DrugKnowledgeModule.hpp"

#include "agent/DrugKnowledgeInferenceAgent.hpp"

using namespace drugKnowledgeModule;

SC_MODULE_REGISTER(DrugKnowledgeModule)->Agent<DrugKnowledgeInferenceAgent>();
