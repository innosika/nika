#pragma once

#include <sc-memory/sc_keynodes.hpp>

namespace spaceKnowledgeModule
{

class SpaceKnowledgeKeynodes : public ScKeynodes
{
public:
  // Класс действий «вывести новые знания о космических объектах».
  static inline ScKeynode const action_infer_space_knowledge{"action_infer_space_knowledge", ScType::ConstNodeClass};

  // Набор логических правил вывода (импликаций), которые применяет агент.
  static inline ScKeynode const concept_space_knowledge_rule{"concept_space_knowledge_rule", ScType::ConstNodeClass};

};

}  // namespace spaceKnowledgeModule
