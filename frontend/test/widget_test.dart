import 'package:flutter_test/flutter_test.dart';

import 'package:doc2graph_frontend/main.dart';

void main() {
  testWidgets('renders local inspector shell', (WidgetTester tester) async {
    await tester.pumpWidget(const Doc2GraphApp());

    expect(find.text('Doc2Graph Local Inspector'), findsOneWidget);
    expect(find.text('Run Wikipedia Fixture Job'), findsOneWidget);
  });
}
