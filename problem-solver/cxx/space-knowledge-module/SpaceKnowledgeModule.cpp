#include "SpaceKnowledgeModule.hpp"

#include "agent/SpaceKnowledgeInferenceAgent.hpp"

using namespace spaceKnowledgeModule;

SC_MODULE_REGISTER(SpaceKnowledgeModule)->Agent<SpaceKnowledgeInferenceAgent>();
