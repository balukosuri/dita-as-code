<?xml version="1.0" encoding="UTF-8"?>
<!--
  House rules for DITA, expressed as Schematron.

  Why Schematron and why here: it is the only practical way to enforce structural style in
  DITA, and it belongs in CI rather than the editor. Editor support is almost nonexistent -
  the lemminx Schematron bridge has a few hundred installs. Oxygen has first-class support
  if you have a licence.

  Run it with SchXslt, which is free:

      java -jar schxslt-cli.jar -d topic.dita -s config/schematron/house-rules.sch -e

  The -e flag makes a rule violation exit non-zero, which is what makes this a gate rather
  than a report. Do NOT rely on the schematron option of xmllint: it implements only a
  subset of ISO Schematron and is unreliable for abstract patterns and phases.

  These rules are a starting point. Delete what does not match your house style rather than
  working around it - a rule nobody believes in gets disabled, and then all of them do.
-->
<schema xmlns="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt2">

  <title>DITA house rules</title>

  <phase id="structure">
    <active pattern="task-structure"/>
    <active pattern="list-sanity"/>
    <active pattern="id-required"/>
  </phase>

  <phase id="style">
    <active pattern="semantic-markup"/>
    <active pattern="accessibility"/>
  </phase>

  <pattern id="task-structure">
    <title>Task topics follow the expected shape</title>
    <rule context="task/taskbody">
      <assert test="steps or steps-unordered or steps-informal" role="error">
        A task must contain steps. If this topic does not describe a procedure, it is
        probably a concept or a reference topic rather than a task.
      </assert>
    </rule>
    <rule context="step">
      <assert test="cmd" role="error">
        Every step needs a cmd element carrying the instruction.
      </assert>
      <report test="normalize-space(cmd) = ''" role="error">
        This step's cmd is empty.
      </report>
    </rule>
  </pattern>

  <pattern id="list-sanity">
    <title>Lists have more than one item</title>
    <rule context="ul | ol">
      <report test="count(li) = 1" role="warning">
        A list with a single item is usually a paragraph. Consider rewriting it as one.
      </report>
    </rule>
  </pattern>

  <pattern id="id-required">
    <title>Topics and referenceable elements carry IDs</title>
    <rule context="/*[contains(@class, 'topic/topic')]">
      <assert test="@id" role="error">
        Every topic needs an @id. Without one it cannot be cross-referenced or conref'd.
      </assert>
    </rule>
  </pattern>

  <pattern id="semantic-markup">
    <title>Use semantic elements rather than plain text</title>
    <rule context="p | li | cmd">
      <!-- Semantic markup is what makes DITA worth the tag overhead. A path in a <p> as
           bare text cannot be styled, extracted or tested; the same path in <filepath>
           can be all three. -->
      <report test="matches(., '(^|\s)(/[A-Za-z0-9_.\-]+){2,}(\s|$)') and not(filepath)"
              role="info">
        This looks like a file path. Consider wrapping it in filepath so it can be styled
        and validated.
      </report>
    </rule>
    <rule context="uicontrol">
      <report test="normalize-space(.) = ''" role="warning">
        Empty uicontrol - the UI label is missing.
      </report>
    </rule>
  </pattern>

  <pattern id="accessibility">
    <title>Images carry alternative text</title>
    <rule context="image">
      <assert test="alt or @alt or normalize-space(.) != ''" role="error">
        Every image needs alternative text. This is an accessibility requirement, not a
        style preference.
      </assert>
    </rule>
  </pattern>

</schema>
