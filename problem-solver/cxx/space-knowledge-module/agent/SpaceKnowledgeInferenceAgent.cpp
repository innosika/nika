#include "SpaceKnowledgeInferenceAgent.hpp"

#include "keynodes/SpaceKnowledgeKeynodes.hpp"

#include <common/utils/ActionUtils.hpp>
#include <inference/inference_manager_factory.hpp>
#include <sc-agents-common/utils/IteratorUtils.hpp>

namespace spaceKnowledgeModule
{

SpaceKnowledgeInferenceAgent::SpaceKnowledgeInferenceAgent()
{
  m_logger = utils::ScLogger(
      utils::ScLogger::ScLogType::File, "logs/SpaceKnowledgeInferenceAgent.log", utils::ScLogLevel::Debug, true);
}

ScAddr SpaceKnowledgeInferenceAgent::GetActionClass() const
{
  return SpaceKnowledgeKeynodes::action_infer_space_knowledge;
}

// Выведенный факт — это дуга принадлежности из отношения к паре (следствие вида «_a _=> nrel_x:: _b»)
// или из класса к экземпляру (следствие вида «_class _-> _instance»).
size_t SpaceKnowledgeInferenceAgent::CountDerivedFacts(ScAddr const & outputStructure) const
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

ScResult SpaceKnowledgeInferenceAgent::DoProgram(ScActionInitiatedEvent const & event, ScAction & action)
{
  ScAddr const & objectsSet = action.GetArgument(ScKeynodes::rrel_1);
  size_t objectsCount = 0;
  if (objectsSet.IsValid())
  {
    ScIterator3Ptr const it = m_context.CreateIterator3(objectsSet, ScType::ConstPermPosArc, ScType::ConstNode);
    while (it->Next())
      ++objectsCount;
  }
  m_logger.Info("Вывод новых знаний, объектов с новыми сведениями: " + std::to_string(objectsCount));

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
  // Правила зависят друг от друга (класс объекта выводится первым правилом и нужен правилу о спутниках; принадлежность к планетной системе распространяется по цепочке орбит),
  // поэтому набор применяется повторно, пока появляются новые факты.
  for (int iteration = 1; iteration <= MAX_ITERATIONS; ++iteration)
  {
    ScAddr const & outputStructure = m_context.GenerateNode(ScType::ConstNodeStructure);
    inference::InferenceParams const inferenceParams{
        SpaceKnowledgeKeynodes::concept_space_knowledge_rule, {}, {}, outputStructure};
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

}  // namespace spaceKnowledgeModule
