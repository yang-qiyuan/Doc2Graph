import 'package:flutter_test/flutter_test.dart';

import 'package:doc2graph_frontend/main.dart';

void main() {
  testWidgets('renders local inspector shell', (WidgetTester tester) async {
    await tester.pumpWidget(const Doc2GraphApp());

    expect(find.text('Doc2Graph Local Inspector'), findsOneWidget);
    expect(find.text('Run Wikipedia Fixture Job'), findsOneWidget);
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
      sourceDoc: 'doc-1',
      mentions: const [],
    );
    final secondaryPerson = EntityModel(
      id: 'E2',
      name: 'Morehouse College',
      type: 'Person',
      sourceDoc: 'doc-1',
      mentions: const [],
    );
    final place = EntityModel(
      id: 'E3',
      name: 'Atlanta',
      type: 'Place',
      sourceDoc: 'doc-1',
      mentions: const [],
    );

    expect(isMajorGraphEntity(primary, documents), isTrue);
    expect(isMajorGraphEntity(secondaryPerson, documents), isFalse);
    expect(isMajorGraphEntity(place, documents), isFalse);
  });
}
