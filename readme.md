# Doc2Graph Project
## Function Description
1. Given a bunch of files (in this prototype: Wikipedia biological entities), either in PDF version or markdown version (maybe serveral urls)
2. Deal with the files in parallel (parsing, formalizing, stored in DB)
3. Core Agentic Loop: a loop for iteratively refine the extraction of relationships and the generation of json file that used for visualization.
4. Output and visualizations
   1. On the output, in order to ensure verifiability and reduce model hallucination, add a floating window displayed when the mouse is on the node that displays the source of the element
   2. After clicking on the node, source is presented with hightlight on the detailed chunk of extracted text
   3. graphs with node connected by edges
## Detailed Requirements
- Cap for file uploadings: for this prototype, at most 30 files. But it could be expanded later.
- Make sure to ensure the schema is minimized. First you need to define some non-overlapping relationships (e.g., born_in, worked_at, authored, influenced_by) and then check if they have overlaps.
  - Here are the predefined the entities and relations to folow:
  ``
  PERSON-PERSON: influenced_by, collaborated_with, family_of, student_of
   PERSON-ORG: worked_at, studied_at, founded, member_of  
   PERSON-PLACE: born_in, died_in, lived_in
   PERSON-WORK: authored, translated, edited
   PERSON-TIME: born_on, died_on
    ``
- For the schema, make sure to use unique ID to represent entity.
- Write unit tests to test the implementation if necessary.
  
**An Example Schema:**
```
{
  "entities": [
    {
      "id": "E1",
      "name": "鲁迅",
      "type": "Person",
      "aliases": ["周树人"],
      "source_doc": "doc_001",          // ← 来自哪个文档
      "mentions": [                       // ← 在文档中的位置(支持你的高亮功能)
        {"doc_id": "doc_001", "char_start": 120, "char_end": 122}
      ]
    }
  ],
  "relations": [
    {
      "id": "R1",                         // ← relation也要ID,方便引用
      "subject": "E1",
      "predicate": "worked_at",
      "object": "E2",
      "evidence": "鲁迅曾在北京大学任教",
      "source_doc": "doc_001",
      "char_start": 450,                  // ← 关键!实现"点击高亮原文"必须有
      "char_end": 462,
      "confidence": 0.92                  // ← LLM返回的置信度,方便后续过滤
    }
  ]
}
```
## Architecture
### FrontEnd
- Flutter
### BackEnd
- Go
### Graph Database
- Neo4j
### LLM caller
- Python for the core agentic loop
### Deployment
- Docker

### Things not needed
- User Authentication System
- Prompt Injection and malicious usage prevention component

### A Starting Point: 
You can start with 10-20 Wikipedia biographical entries and run through the complete pipeline of 'entity recognition → relation extraction → triple normalization → graph construction

### Next Step:
should add a test set to test the ability of relation extraction
should make the nodes that are connected move together when dragged the main node (entity)