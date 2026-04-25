import 'package:flutter_test/flutter_test.dart';

import 'package:doc2graph_frontend/main.dart';

void main() {
  testWidgets('renders local inspector shell', (WidgetTester tester) async {
    await tester.pumpWidget(const Doc2GraphApp());

    expect(find.text('Doc2Graph Local Inspector'), findsOneWidget);
    expect(find.text('Choose Markdown Files'), findsOneWidget);
    expect(find.text('Run Test Fixture'), findsOneWidget);
  });

  test('major graph entities are primary document people only', () {
    final documents = [
      DocumentModel(
        id: 'doc-1',
        title: 'Martin Luther King Jr.',
        sourceType: 'markdown',
      ),
    ];

    final primary = EntityModel(
      id: 'E1',
      name: 'Martin Luther King Jr.',
      type: 'Person',
      sourceDoc: 'normalized-source',
      mentions: [MentionModel(docId: 'doc-1', charStart: 0, charEnd: 22)],
    );
    final secondaryPerson = EntityModel(
      id: 'E2',
      name: 'Morehouse College',
      type: 'Person',
      sourceDoc: 'doc-1',
      mentions: [MentionModel(docId: 'doc-1', charStart: 40, charEnd: 57)],
    );
    final place = EntityModel(
      id: 'E3',
      name: 'Atlanta',
      type: 'Place',
      sourceDoc: 'doc-1',
      mentions: [MentionModel(docId: 'doc-1', charStart: 80, charEnd: 87)],
    );
    final aliasedPrimary = EntityModel(
      id: 'E4',
      name: 'Michael King Jr.',
      type: 'Person',
      sourceDoc: 'doc-2',
      mentions: [MentionModel(docId: 'doc-1', charStart: 0, charEnd: 22)],
      aliases: const ['Martin Luther King Jr.'],
    );

    expect(isMajorGraphEntity(primary, documents), isTrue);
    expect(isMajorGraphEntity(secondaryPerson, documents), isFalse);
    expect(isMajorGraphEntity(place, documents), isFalse);
    expect(isMajorGraphEntity(aliasedPrimary, documents), isTrue);
  });

  test('stale relation predicate filters fall back to all relations', () {
    expect(
      effectivePredicateFilter('student_of', const ['all', 'born_in']),
      'all',
    );
    expect(
      effectivePredicateFilter('born_in', const ['all', 'born_in']),
      'born_in',
    );
  });

  test('upload drafts infer stable ids and titles', () {
    final draft = buildUploadDraft(
      filename: 'Ada_Lovelace.md',
      content: '# Ada Lovelace\n\nAda was a mathematician.',
      index: 0,
    );

    expect(draft.id, 'upload-001-ada-lovelace');
    expect(draft.title, 'Ada Lovelace');
    expect(draft.toJson()['source_type'], 'markdown');
    expect(draft.toJson()['content'], contains('mathematician'));
  });

  test('upload draft title falls back to filename', () {
    final draft = buildUploadDraft(
      filename: 'Isaac-Newton.markdown',
      content: 'No heading here.',
      index: 4,
    );

    expect(draft.id, 'upload-005-isaac-newton');
    expect(draft.title, 'Isaac Newton');
  });

  test('upload validation catches unsupported and empty files', () {
    final unsupported = buildUploadDraft(
      filename: 'notes.pdf',
      content: 'PDF bytes are not accepted here.',
      index: 0,
    );
    final empty = buildUploadDraft(
      filename: 'empty.md',
      content: '   ',
      index: 1,
    );

    final issues = validateUploadDrafts([unsupported, empty]);

    expect(issues.map((issue) => issue.filename), contains('notes.pdf'));
    expect(issues.map((issue) => issue.filename), contains('empty.md'));
    expect(
      issues.map((issue) => issue.message),
      contains('Only .md, .markdown, and .txt files are supported.'),
    );
    expect(issues.map((issue) => issue.message), contains('File is empty.'));
  });

  test('upload validation enforces 30 file cap', () {
    final drafts = List.generate(
      31,
      (index) => buildUploadDraft(
        filename: 'doc_$index.md',
        content: '# Doc $index\n\nText',
        index: index,
      ),
    );

    final issues = validateUploadDrafts(drafts);

    expect(issues, hasLength(1));
    expect(issues.single.filename, 'Selection');
    expect(issues.single.message, contains('Choose at most 30 files'));
  });
}
