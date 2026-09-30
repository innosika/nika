#pragma once

#include <sc-memory/sc_agent.hpp>

namespace spaceKnowledgeModule
{

/*
 * Агент вывода новых знаний о космических объектах.
 * Условие инициирования: появление дуги из action_initiated в действие класса action_infer_space_knowledge.
 * Аргумент rrel_1 (необязательный): множество объектов, о которых только что погружены сведения, —
 * используется для отчёта; правила применяются ко всей базе знаний.
 * Результат: структура с выведенными фактами и sc-ссылкой с их числом.
 */
class SpaceKnowledgeInferenceAgent : public ScActionInitiatedAgent
{
public:
  SpaceKnowledgeInferenceAgent();

  ScAddr GetActionClass() const override;

  ScResult DoProgram(ScActionInitiatedEvent const & event, ScAction & action) override;

private:
  static int const MAX_ITERATIONS = 3;

  size_t CountDerivedFacts(ScAddr const & outputStructure) const;
};

}  // namespace spaceKnowledgeModule
