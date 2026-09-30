#pragma once

#include <sc-memory/sc_agent.hpp>

#include "keynodes/MessageKeynodes.hpp"
#include <map>

namespace dialogControlModule
{

enum VariableType
{
  LINK = 1,
  SET_ELEMENTS = 2,
  SET_POWER = 3,
  CLASS_FIND = 4,
  SUBAREA_FIND = 5,
  LIST_VALUES = 6
};

class PhraseGenerationAgent : public ScActionInitiatedAgent
{
public:
  PhraseGenerationAgent();

  ScAddr GetActionClass() const override;

  ScResult DoProgram(ScActionInitiatedEvent const & event, ScAction & action) override;

private:
  const std::string VAR_CONST = "var";
  const std::string VAR_REGULAR = R"(\$\{var\})";
  const std::string LINK_VAR_REGULAR = R"(\$\{_\w+\})";
  const std::string SET_ELEMENTS_VAR_REGULAR = R"(\$...\{_\w+\})";
  const std::string SET_POWER_REGULAR = R"(\$set_power\{_\w+\})";
  const std::string SET_POWER_VAR_REGULAR = R"(\$set_power\{var\})";
  const std::string CLASS_REGULAR = R"(\$superclass_find\{_\w+\})";
  const std::string CLASS_VAR_REGULAR = R"(\$superclass_find\{var\})";
  const std::string SUBAREA_REGULAR = R"(\$subarea_find\{_\w+\})";
  const std::string SUBAREA_VAR_REGULAR = R"(\$subarea_find\{var\})";
  // $list{_x} — все различные значения переменной _x по всем согласованным результатам поиска
  // по шаблону фразы (содержимое ссылки или основной идентификатор), через запятую
  const std::string LIST_VALUES_REGULAR = R"(\$list\{_\w+\})";
  const std::string LIST_VALUES_VAR_REGULAR = R"(\$list\{var\})";
  const size_t LIST_VALUES_MAX_RESULTS = 500;

  ScAddrVector notSearchable;

  void findNotSearchableElements();

  ScAddr generateLinkByTemplate(
      const ScAddr & templateNode,
      const ScAddr & parametersNode,
      const ScAddr & textTemplateLink);

  std::map<VariableType, std::vector<std::string>> getTemplateVariables(std::string const & text);

  std::string findResultText(
      ScAddr const & templateNode,
      ScAddr const & parametersNode,
      std::map<VariableType, std::vector<std::string>> const & variables,
      std::string const & text);

  std::vector<ScTemplateParams> findParametersList(const ScAddr & templateNode, const ScAddr & parametersNode);
  std::vector<std::string> getVariableNames(std::string const & text, std::string regular_str);

  std::string processScTemplate(
      ScAddr const & templateNode,
      ScTemplateParams const & parameters,
      std::map<VariableType, std::vector<std::string>> const & variables,
      std::string const & text);

  std::vector<std::string> getTemplateVariableNames(ScAddr const & templateNode);

  bool isResultConsistent(
      ScAddr const & templateNode,
      std::vector<std::string> const & variableNames,
      ScTemplateSearchResultItem const & item);

  std::string generatePhraseAnswer(
      ScTemplateSearchResultItem const & phraseSemanticResult,
      std::map<VariableType, std::vector<std::string>> const & variables,
      std::string const & text);

  void replaceLinksVariables(
      ScTemplateSearchResultItem const & phraseSemanticResult,
      std::vector<std::string> const & variables,
      std::string & text);

  void replaceSetElementsVariables(
      ScTemplateSearchResultItem const & phraseSemanticResult,
      std::vector<std::string> const & variables,
      std::string & text);

  void replaceSetPowerVariables(
      ScTemplateSearchResultItem const & phraseSemanticResult,
      std::vector<std::string> const & variables,
      std::string & text);

  void replaceClassVariables(
      ScTemplateSearchResultItem const & phraseSemanticResult,
      std::vector<std::string> const & variables,
      std::string & text);

  void replaceSubareaVariables(
      ScTemplateSearchResultItem const & phraseSemanticResult,
      std::vector<std::string> const & variables,
      std::string & text);

  std::string getElementText(ScAddr const & element);

  void generateSemanticEquivalent(const ScAddr & replyMessageNode, const ScAddr & structure);

  void updateSemanticAnswer(const ScTemplateSearchResultItem & phraseSemanticResult);

  void updateSemanticAnswer(const ScAddr & phraseAddr);
};

}  // namespace dialogControlModule
