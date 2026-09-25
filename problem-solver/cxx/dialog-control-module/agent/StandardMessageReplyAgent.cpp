#include "StandardMessageReplyAgent.hpp"

#include "keynodes/DialogKeynodes.hpp"
#include "keynodes/MessageKeynodes.hpp"
#include <common/utils/ActionUtils.hpp>
#include <sc-agents-common/utils/CommonUtils.hpp>
#include <sc-agents-common/utils/IteratorUtils.hpp>

#include <algorithm>

using namespace utils;

namespace dialogControlModule
{

StandardMessageReplyAgent::StandardMessageReplyAgent()
{
  m_logger = utils::ScLogger(
      utils::ScLogger::ScLogType::File, "logs/StandardMessageReplyAgent.log", utils::ScLogLevel::Debug, true);
}

ScResult StandardMessageReplyAgent::DoProgram(ScActionInitiatedEvent const & event, ScAction & action)
{
  ScAddr messageNode = action.GetArgument(ScKeynodes::rrel_1);
  if (!messageNode.IsValid())
  {
    m_logger.Debug("The action doesn't have a message node");
  }

  ScAddr logicRuleNode = generateReplyMessage(messageNode);
  if (!m_context.IsElement(logicRuleNode))
  {
    m_logger.Warning(
        "The reply message isn't generated because reply construction wasn't found through direct inference agent. "
        "Trying to generate default reply message");
    // Прежняя версия заменяла байт replyText[length - 2] на '.', разрезая двухбайтовую букву «в»
    // в UTF-8: sc-server падал при сериализации такой ссылки в JSON, а собранные классы в текст
    // не попадали. Теперь в ответ выводятся основные идентификаторы классов сообщения и
    // выделенные в нём сущности.
    std::stringstream setElementsTextStream;
    setElementsTextStream << "Извините, я не нашла ответа на Ваш вопрос.";
    auto const & nameOf = [this](ScAddr const & element) -> std::string
    {
      std::string name = utils::CommonUtils::getMainIdtf(&m_context, element, {ScKeynodes::lang_ru});
      return name.empty() ? m_context.GetElementSystemIdentifier(element) : name;
    };
    auto const & joinNames = [](std::vector<std::string> const & names) -> std::string
    {
      std::string joined;
      for (std::string const & name : names)
        joined += (joined.empty() ? "" : ", ") + name;
      return joined;
    };
    std::vector<std::string> messageClasses;
    ScIterator3Ptr it3 = m_context.CreateIterator3(ScType::ConstNodeClass, ScType::ConstPermPosArc, messageNode);
    while (it3->Next())
    {
      if (it3->Get(0) == MessageKeynodes::concept_message)
        continue;
      std::string const name = nameOf(it3->Get(0));
      if (!name.empty())
        messageClasses.push_back(name);
    }
    std::sort(messageClasses.begin(), messageClasses.end());
    if (!messageClasses.empty())
      setElementsTextStream << " Я определила, что данное сообщение является элементом классов: "
                            << joinNames(messageClasses) << ".";
    std::vector<std::string> messageEntities;
    ScIterator5Ptr it5 = m_context.CreateIterator5(
        messageNode, ScType::ConstPermPosArc, ScType::Unknown, ScType::ConstPermPosArc, MessageKeynodes::rrel_entity);
    while (it5->Next())
    {
      std::string const name = nameOf(it5->Get(2));
      if (!name.empty())
        messageEntities.push_back(name);
    }
    if (!messageEntities.empty())
      setElementsTextStream << " Выделенные сущности: " << joinNames(messageEntities) << ".";
    ScAddr const & defaultReplyMessage = m_context.GenerateNode(ScType::NodeConst);
    ScAddr const & defaultReplyLink = m_context.GenerateLink(ScType::LinkConst);
    std::string const replyText = setElementsTextStream.str();
    m_context.SetLinkContent(defaultReplyLink, replyText);
    ScTemplate templ;
    templ.Triple(ScKeynodes::lang_ru, ScType::VarPermPosArc, defaultReplyLink);
    templ.Triple(ScType::VarNode >> "_link", ScType::VarPermPosArc, defaultReplyLink);
    templ.Quintuple(
        "_link",
        ScType::VarCommonArc,
        defaultReplyMessage,
        ScType::VarPermPosArc,
        DialogKeynodes::nrel_sc_text_translation);
    templ.Quintuple(
        messageNode, ScType::VarCommonArc, defaultReplyMessage, ScType::VarPermPosArc, MessageKeynodes::nrel_reply);
    ScTemplateResultItem result;
    m_context.GenerateByTemplate(templ, result);
    action.SetResult(defaultReplyMessage);
    return action.FinishSuccessfully();
  }
  ScAddr replyMessageNode = IteratorUtils::getAnyByOutRelation(&m_context, messageNode, MessageKeynodes::nrel_reply);
  m_context.GenerateConnector(ScType::ConstPermPosArc, MessageKeynodes::concept_message, replyMessageNode);
  if (!replyMessageNode.IsValid())
  {
    m_logger.Error("The reply message isn't generated");
    return action.FinishUnsuccessfully();
  }

  m_logger.Debug("The reply message is generated");

  initFields();
  ScAddr langNode = langSearcher->getMessageLanguage(messageNode);

  ScAddr parametersNode = generatePhraseAgentParametersNode(messageNode);

  if (!messageHandler->processReplyMessage(replyMessageNode, logicRuleNode, langNode, parametersNode))
  {
    m_logger.Error("The reply message is formed incorrectly");
    ScIterator5Ptr it5 = IteratorUtils::getIterator5(&m_context, replyMessageNode, MessageKeynodes::nrel_reply, false);
    if (it5->Next())
    {
      m_context.EraseElement(it5->Get(1));
    }

    return action.FinishUnsuccessfully();
  }
  ScAddr responseNode = action.GetArgument(ScKeynodes::rrel_2);

  if (m_context.IsElement(responseNode))
    m_context.GenerateConnector(ScType::ConstTempPosArc, responseNode, replyMessageNode);

  action.SetResult(replyMessageNode);
  return action.FinishSuccessfully();
}

ScAddr StandardMessageReplyAgent::GetActionClass() const
{
  return MessageKeynodes::action_standard_message_reply;
}

ScAddr StandardMessageReplyAgent::generateReplyMessage(const ScAddr & messageNode)
{
  ScAddr logicRuleNode;
  ScAddrVector argsVector = {
      MessageKeynodes::template_reply_target,
      MessageKeynodes::concept_answer_on_standard_message_rule_class_by_priority,
      wrapInSet(messageNode)};

  ScAction actionDirectInference =
      ActionUtils::CreateAction(&m_context, MessageKeynodes::action_direct_inference, argsVector);
  bool const result = actionDirectInference.InitiateAndWait(DIRECT_INFERENCE_AGENT_WAIT_TIME);
  if (result)
  {
    if (actionDirectInference.IsFinishedSuccessfully())
    {
      ScAddr answer = IteratorUtils::getAnyByOutRelation(&m_context, actionDirectInference, ScKeynodes::nrel_result);
      ScAddr solutionNode = IteratorUtils::getAnyFromSet(&m_context, answer);
      ScAddr solutionTreeRoot = IteratorUtils::getAnyByOutRelation(&m_context, solutionNode, ScKeynodes::rrel_1);
      if (solutionTreeRoot.IsValid())
      {
        ScAddr argNode = IteratorUtils::getAnyFromSet(&m_context, solutionTreeRoot);
        ScAddrVector arguments;
        ScIterator3Ptr argIt = m_context.CreateIterator3(argNode, ScType::ConstPermPosArc, ScType::VarNode);
        while (argIt->Next())
        {
          ScAddrVector arguments;
          arguments.push_back(argIt->Get(2));
        }
        logicRuleNode = IteratorUtils::getAnyByOutRelation(&m_context, solutionTreeRoot, ScKeynodes::rrel_1);
      }
    }
  }
  return logicRuleNode;
}

ScAddr StandardMessageReplyAgent::wrapInSet(ScAddr const & addr)
{
  ScAddr set = m_context.GenerateNode(ScType::ConstNodeTuple);
  m_context.GenerateConnector(ScType::ConstPermPosArc, set, addr);
  return set;
}

ScAddr StandardMessageReplyAgent::generatePhraseAgentParametersNode(const ScAddr & messageNode)
{
  ScAddrVector parameters;
  parameters.push_back(messageNode);

  ScAddr authorNode = messageSearcher->getMessageAuthor(messageNode);
  if (authorNode.IsValid())
    parameters.push_back(authorNode);

  ScAddr themeNode = messageSearcher->getMessageTheme(messageNode);
  if (themeNode.IsValid())
    parameters.push_back(themeNode);

  ScAddr parametersNode = m_context.GenerateNode(ScType::ConstNode);
  for (auto & node : parameters)
  {
    if (!m_context.CheckConnector(parametersNode, node, ScType::ConstPermPosArc))
      m_context.GenerateConnector(ScType::ConstPermPosArc, parametersNode, node);
  }

  return parametersNode;
}

void StandardMessageReplyAgent::initFields()
{
  this->langSearcher = std::make_unique<LanguageSearcher>(&m_context, &m_logger);
  this->messageSearcher = std::make_unique<commonModule::MessageSearcher>(&m_context, &m_logger);
  this->messageHandler = std::make_unique<MessageHandler>(&m_context, &m_logger);
}

}  // namespace dialogControlModule
