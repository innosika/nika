#include "DrugKnowledgeInferenceAgent.hpp"

#include "keynodes/DrugKnowledgeKeynodes.hpp"

#include <common/utils/ActionUtils.hpp>
#include <inference/inference_manager_factory.hpp>
#include <sc-agents-common/utils/IteratorUtils.hpp>

namespace drugKnowledgeModule
{

DrugKnowledgeInferenceAgent::DrugKnowledgeInferenceAgent()
{
  m_logger = utils::ScLogger(
      utils::ScLogger::ScLogType::File, "logs/DrugKnowledgeInferenceAgent.log", utils::ScLogLevel::Debug, true);
}

ScAddr DrugKnowledgeInferenceAgent::GetActionClass() const
{
  return DrugKnowledgeKeynodes::action_infer_drug_knowledge;
}

// Выведенный факт — это дуга принадлежности из отношения к паре (следствие вида «_a _=> nrel_x:: _b»)
// или из класса к экземпляру (следствие вида «_class _-> _instance»).
size_t DrugKnowledgeInferenceAgent::CountDerivedFacts(ScAddr const & outputStructure) const
{
  size_t count = 0;
  ScIterator3Ptr const it = m_context.CreateIterator3(outputStructure, ScType::ConstPermPosArc, ScType::Unknown);
  while (it->Next())
  {
    ScAddr const & element = it->Get(2);
    if (m_context.GetElementType(element) != ScType::ConstPermPosArc)
      continue;
    auto const [source, target] = m_context.GetConnectorIncidentElements(element);
    ScType const sourceType = m_context.GetElementType(source);
    ScType const targetType = m_context.GetElementType(target);
    if (sourceType == ScType::ConstNodeNonRole && targetType.IsConnector())
      ++count;
    else if (sourceType == ScType::ConstNodeClass && targetType.IsNode())
      ++count;
  }
  return count;
}

ScResult DrugKnowledgeInferenceAgent::DoProgram(ScActionInitiatedEvent const & event, ScAction & action)
{
  ScAddr const & drugsSet = action.GetArgument(ScKeynodes::rrel_1);
  size_t drugsCount = 0;
  if (drugsSet.IsValid())
  {
    ScIterator3Ptr const it = m_context.CreateIterator3(drugsSet, ScType::ConstPermPosArc, ScType::ConstNode);
    while (it->Next())
      ++drugsCount;
  }
  m_logger.Info("Вывод новых знаний, препаратов с новыми сведениями: " + std::to_string(drugsCount));

  // GENERATE_UNIQUE_FORMULAS + SEARCH_WITH_REPLACEMENTS: следствие не генерируется, если такой факт уже есть;
  // REPLACEMENTS_ALL: правило применяется ко всем подстановкам, а не к первой найденной.
  inference::InferenceConfig const inferenceConfig{
      inference::GENERATE_UNIQUE_FORMULAS,
      inference::REPLACEMENTS_ALL,
      inference::TREE_ONLY_OUTPUT_STRUCTURE,
      inference::SEARCH_IN_ALL_KB,
      inference::GENERATED_ONLY,
      inference::SEARCH_WITH_REPLACEMENTS};

  ScAddrVector answerElements;
  size_t totalFacts = 0;
  // Правила зависят друг от друга (класс препарата выводится первым правилом и нужен следующим),
  // поэтому набор применяется повторно, пока появляются новые факты.
  for (int iteration = 1; iteration <= MAX_ITERATIONS; ++iteration)
  {
    ScAddr const & outputStructure = m_context.GenerateNode(ScType::ConstNodeStructure);
    inference::InferenceParams const inferenceParams{
        DrugKnowledgeKeynodes::concept_drug_knowledge_rule, {}, {}, outputStructure};
    std::unique_ptr<inference::InferenceManagerAbstract> manager =
        inference::InferenceManagerFactory::ConstructDirectInferenceManagerAll(&m_context, &m_logger, inferenceConfig);
    try
    {
      manager->ApplyInference(inferenceParams);
    }
    catch (utils::ScException const & exception)
    {
      m_logger.Error(exception.Description());
      ActionUtils::wrapActionResultToScStructure(&m_context, action, answerElements);
      return action.FinishUnsuccessfully();
    }
    size_t const facts = CountDerivedFacts(outputStructure);
    m_logger.Info("Итерация " + std::to_string(iteration) + ": выведено фактов " + std::to_string(facts));
    answerElements.push_back(outputStructure);
    totalFacts += facts;
    if (facts == 0)
      break;
  }

  ScAddr const & countLink = m_context.GenerateLink(ScType::ConstNodeLink);
  m_context.SetLinkContent(countLink, std::to_string(totalFacts));
  answerElements.push_back(countLink);
  ActionUtils::wrapActionResultToScStructure(&m_context, action, answerElements);
  m_logger.Info("Всего выведено фактов: " + std::to_string(totalFacts));
  return action.FinishSuccessfully();
}

}  // namespace drugKnowledgeModule
