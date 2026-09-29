#pragma once

#include <sc-memory/sc_keynodes.hpp>

namespace drugKnowledgeModule
{

class DrugKnowledgeKeynodes : public ScKeynodes
{
public:
  // Класс действий «вывести новые знания о лекарственных средствах».
  static inline ScKeynode const action_infer_drug_knowledge{"action_infer_drug_knowledge", ScType::ConstNodeClass};

  // Набор логических правил вывода (импликаций), которые применяет агент.
  static inline ScKeynode const concept_drug_knowledge_rule{"concept_drug_knowledge_rule", ScType::ConstNodeClass};

  static inline ScKeynode const concept_drug{"concept_drug", ScType::ConstNodeClass};
};

}  // namespace drugKnowledgeModule
