import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const Doc2GraphApp());
}

class Doc2GraphApp extends StatelessWidget {
  const Doc2GraphApp({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF0B6E4F)),
      useMaterial3: true,
    );

    return MaterialApp(
      title: 'Doc2Graph',
      debugShowCheckedModeBanner: false,
      theme: theme,
      home: const ProjectHomePage(),
    );
  }
}

class ProjectHomePage extends StatefulWidget {
  const ProjectHomePage({super.key});

  @override
  State<ProjectHomePage> createState() => _ProjectHomePageState();
}

class _ProjectHomePageState extends State<ProjectHomePage> {
  static const _defaultBaseUrl = String.fromEnvironment(
    'DOC2GRAPH_API_BASE',
    defaultValue: 'http://127.0.0.1:8080',
  );

  late final TextEditingController _baseUrlController;
  final Doc2GraphApi _api = Doc2GraphApi();

  bool _isLoading = false;
  String? _error;
  JobResponse? _job;
  GraphData? _graph;
  EntityModel? _selectedEntity;
  RelationEvidence? _selectedEvidence;
  late final ValueNotifier<EntityModel?> _hoveredEntity;
  late final ValueNotifier<RelationModel?> _hoveredRelation;
  double _minConfidence = 0.0;
  String _predicateFilter = 'all';

  @override
  void initState() {
    super.initState();
    _baseUrlController = TextEditingController(text: _defaultBaseUrl);
    _hoveredEntity = ValueNotifier<EntityModel?>(null);
    _hoveredRelation = ValueNotifier<RelationModel?>(null);
  }

  @override
  void dispose() {
    _baseUrlController.dispose();
    _hoveredEntity.dispose();
    _hoveredRelation.dispose();
    super.dispose();
  }

  Future<void> _runWikipediaFixtures() async {
    setState(() {
      _isLoading = true;
      _error = null;
      _selectedEntity = null;
      _selectedEvidence = null;
    });
    _hoveredEntity.value = null;
    _hoveredRelation.value = null;

    try {
      final baseUrl = _normalizedBaseUrl;
      final job = await _api.createWikipediaFixtureJob(baseUrl);
      final graph = await _api.fetchGraph(baseUrl, job.job.id);
      setState(() {
        _job = job;
        _graph = graph;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _selectEntity(EntityModel entity) async {
    if (_job == null) {
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
      _selectedEvidence = null;
    });

    try {
      final detailedEntity = await _api.fetchEntity(
        _normalizedBaseUrl,
        _job!.job.id,
        entity.id,
      );
      setState(() {
        _selectedEntity = detailedEntity;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _selectRelation(RelationModel relation) async {
    if (_job == null) {
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
      _selectedEntity = null;
    });

    try {
      final evidence = await _api.fetchRelationEvidence(
        _normalizedBaseUrl,
        _job!.job.id,
        relation.id,
      );
      setState(() {
        _selectedEvidence = evidence;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _handleHover({
    EntityModel? entity,
    RelationModel? relation,
  }) {
    if (_hoveredEntity.value?.id == entity?.id &&
        _hoveredRelation.value?.id == relation?.id) {
      return;
    }
    _hoveredEntity.value = entity;
    _hoveredRelation.value = relation;
  }

  String get _normalizedBaseUrl =>
      _baseUrlController.text.trim().replaceAll(RegExp(r'/$'), '');

  List<RelationModel> get _filteredRelations {
    final relations = _graph?.relations ?? const <RelationModel>[];
    return relations.where((relation) {
      if (relation.confidence < _minConfidence) {
        return false;
      }
      if (_predicateFilter != 'all' && relation.predicate != _predicateFilter) {
        return false;
      }
      return true;
    }).toList();
  }

  List<EntityModel> get _filteredEntities {
    final graph = _graph;
    if (graph == null) {
      return const <EntityModel>[];
    }

    final includedIds = <String>{};
    for (final relation in _filteredRelations) {
      includedIds.add(relation.subject);
      includedIds.add(relation.object);
    }
    if (includedIds.isEmpty) {
      return graph.entities;
    }
    return graph.entities
        .where((entity) => includedIds.contains(entity.id))
        .toList();
  }

  List<String> get _availablePredicates {
    final graph = _graph;
    if (graph == null) {
      return const ['all'];
    }
    final predicates = graph.relations.map((e) => e.predicate).toSet().toList()
      ..sort();
    return ['all', ...predicates];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Doc2Graph Local Inspector'),
        backgroundColor: Theme.of(context).colorScheme.surface,
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final isWide = constraints.maxWidth >= 1280;
          final mainPanel = _MainPanel(
            baseUrlController: _baseUrlController,
            isLoading: _isLoading,
            error: _error,
            job: _job,
            graph: _graph,
            filteredEntities: _filteredEntities,
            filteredRelations: _filteredRelations,
            minConfidence: _minConfidence,
            predicateFilter: _predicateFilter,
            availablePredicates: _availablePredicates,
            onMinConfidenceChanged: (value) {
              setState(() {
                _minConfidence = value;
              });
            },
            onPredicateFilterChanged: (value) {
              setState(() {
                _predicateFilter = value;
              });
            },
            onRunWikipediaFixtures: _runWikipediaFixtures,
            onSelectEntity: _selectEntity,
            onSelectRelation: _selectRelation,
            onHover: _handleHover,
          );

          if (!isWide) {
            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                mainPanel,
                const SizedBox(height: 16),
                _DetailPane(
                  selectedEntity: _selectedEntity,
                  selectedEvidence: _selectedEvidence,
                  hoveredEntity: _hoveredEntity,
                  hoveredRelation: _hoveredRelation,
                ),
              ],
            );
          }

          return Row(
            children: [
              Expanded(
                flex: 5,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: mainPanel,
                ),
              ),
              Container(width: 1, color: Theme.of(context).dividerColor),
              Expanded(
                flex: 2,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: _DetailPane(
                    selectedEntity: _selectedEntity,
                    selectedEvidence: _selectedEvidence,
                    hoveredEntity: _hoveredEntity,
                    hoveredRelation: _hoveredRelation,
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _MainPanel extends StatelessWidget {
  const _MainPanel({
    required this.baseUrlController,
    required this.isLoading,
    required this.error,
    required this.job,
    required this.graph,
    required this.filteredEntities,
    required this.filteredRelations,
    required this.minConfidence,
    required this.predicateFilter,
    required this.availablePredicates,
    required this.onMinConfidenceChanged,
    required this.onPredicateFilterChanged,
    required this.onRunWikipediaFixtures,
    required this.onSelectEntity,
    required this.onSelectRelation,
    required this.onHover,
  });

  final TextEditingController baseUrlController;
  final bool isLoading;
  final String? error;
  final JobResponse? job;
  final GraphData? graph;
  final List<EntityModel> filteredEntities;
  final List<RelationModel> filteredRelations;
  final double minConfidence;
  final String predicateFilter;
  final List<String> availablePredicates;
  final ValueChanged<double> onMinConfidenceChanged;
  final ValueChanged<String> onPredicateFilterChanged;
  final Future<void> Function() onRunWikipediaFixtures;
  final ValueChanged<EntityModel> onSelectEntity;
  final ValueChanged<RelationModel> onSelectRelation;
  final void Function({EntityModel? entity, RelationModel? relation}) onHover;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _HeroHeader(),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Backend', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 12),
                TextField(
                  controller: baseUrlController,
                  decoration: const InputDecoration(
                    labelText: 'API Base URL',
                    hintText: 'http://127.0.0.1:8080',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    FilledButton.icon(
                      onPressed: isLoading ? null : onRunWikipediaFixtures,
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('Run Wikipedia Fixture Job'),
                    ),
                    if (isLoading)
                      const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  'Launches the bundled 30-page sample set and reloads the graph canvas from the backend APIs.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                if (error != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ],
              ],
            ),
          ),
        ),
        if (job != null) ...[
          const SizedBox(height: 16),
          _JobSummary(
            job: job!,
            entities: filteredEntities.length,
            relations: filteredRelations.length,
          ),
        ],
        if (graph != null) ...[
          const SizedBox(height: 16),
          _DataSection(
            title: 'Graph Canvas',
            subtitle:
                '${filteredEntities.length} visible nodes • ${filteredRelations.length} visible edges',
            child: Column(
              children: [
                _GraphFilters(
                  minConfidence: minConfidence,
                  predicateFilter: predicateFilter,
                  availablePredicates: availablePredicates,
                  onMinConfidenceChanged: onMinConfidenceChanged,
                  onPredicateFilterChanged: onPredicateFilterChanged,
                ),
                const SizedBox(height: 16),
                _GraphCanvas(
                  entities: filteredEntities,
                  relations: filteredRelations,
                  onSelectEntity: onSelectEntity,
                  onSelectRelation: onSelectRelation,
                  onHover: onHover,
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _DataSection(
            title: 'Legend',
            subtitle: 'Node colors are based on entity type',
            child: Wrap(
              spacing: 12,
              runSpacing: 12,
              children: const [
                _LegendChip(type: 'Person'),
                _LegendChip(type: 'Time'),
                _LegendChip(type: 'Place'),
                _LegendChip(type: 'Organization'),
                _LegendChip(type: 'Work'),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class _HeroHeader extends StatelessWidget {
  const _HeroHeader();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(
          colors: [Color(0xFF0B6E4F), Color(0xFF77B28C)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Inspect document-to-graph results locally',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 10),
          Text(
            'This view now renders the extracted graph directly. Hover nodes or edges for context, click a node for mentions, and click an edge for highlighted evidence.',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Colors.white.withValues(alpha: 0.92),
                ),
          ),
        ],
      ),
    );
  }
}

class _JobSummary extends StatelessWidget {
  const _JobSummary({
    required this.job,
    required this.entities,
    required this.relations,
  });

  final JobResponse job;
  final int entities;
  final int relations;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Wrap(
          spacing: 24,
          runSpacing: 16,
          children: [
            _Metric(label: 'Job ID', value: job.job.id),
            _Metric(label: 'Status', value: job.job.status),
            _Metric(label: 'Documents', value: '${job.documents.length}'),
            _Metric(label: 'Visible Nodes', value: '$entities'),
            _Metric(label: 'Visible Edges', value: '$relations'),
          ],
        ),
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelMedium),
        const SizedBox(height: 6),
        Text(value, style: Theme.of(context).textTheme.titleMedium),
      ],
    );
  }
}

class _DataSection extends StatelessWidget {
  const _DataSection({
    required this.title,
    required this.subtitle,
    required this.child,
  });

  final String title;
  final String subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 16),
            child,
          ],
        ),
      ),
    );
  }
}

class _GraphFilters extends StatelessWidget {
  const _GraphFilters({
    required this.minConfidence,
    required this.predicateFilter,
    required this.availablePredicates,
    required this.onMinConfidenceChanged,
    required this.onPredicateFilterChanged,
  });

  final double minConfidence;
  final String predicateFilter;
  final List<String> availablePredicates;
  final ValueChanged<double> onMinConfidenceChanged;
  final ValueChanged<String> onPredicateFilterChanged;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 24,
      runSpacing: 16,
      alignment: WrapAlignment.spaceBetween,
      children: [
        SizedBox(
          width: 320,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Minimum confidence ${minConfidence.toStringAsFixed(2)}'),
              Slider(
                value: minConfidence,
                min: 0,
                max: 1,
                divisions: 10,
                onChanged: onMinConfidenceChanged,
              ),
            ],
          ),
        ),
        SizedBox(
          width: 260,
          child: DropdownButtonFormField<String>(
            initialValue: predicateFilter,
            decoration: const InputDecoration(
              labelText: 'Relation type',
              border: OutlineInputBorder(),
            ),
            items: availablePredicates
                .map(
                  (predicate) => DropdownMenuItem<String>(
                    value: predicate,
                    child:
                        Text(predicate == 'all' ? 'All relations' : predicate),
                  ),
                )
                .toList(),
            onChanged: (value) {
              if (value != null) {
                onPredicateFilterChanged(value);
              }
            },
          ),
        ),
      ],
    );
  }
}

class _GraphCanvas extends StatefulWidget {
  const _GraphCanvas({
    required this.entities,
    required this.relations,
    required this.onSelectEntity,
    required this.onSelectRelation,
    required this.onHover,
  });

  final List<EntityModel> entities;
  final List<RelationModel> relations;
  final ValueChanged<EntityModel> onSelectEntity;
  final ValueChanged<RelationModel> onSelectRelation;
  final void Function({EntityModel? entity, RelationModel? relation}) onHover;

  @override
  State<_GraphCanvas> createState() => _GraphCanvasState();
}

class _GraphCanvasState extends State<_GraphCanvas> {
  late final TransformationController _controller;
  String? _lastFitSignature;
  GraphLayout? _cachedLayout;
  String? _cachedLayoutSignature;
  RelationModel? _activeRelation;
  double _fittedScale = 0.45;
  Size? _lastViewportSize;
  Size? _lastCanvasSize;
  String? _draggingNodeId;
  int? _dragPointer;
  Offset? _dragOffset;
  Map<String, Offset> _connectedNodeOffsets = {};
  bool _isClampingTransform = false;

  @override
  void initState() {
    super.initState();
    _controller = TransformationController();
    _controller.addListener(_clampTransformToBounds);
  }

  @override
  void dispose() {
    _controller.removeListener(_clampTransformToBounds);
    _controller.dispose();
    super.dispose();
  }

  void _clampTransformToBounds() {
    if (_isClampingTransform) {
      return;
    }
    final viewportSize = _lastViewportSize;
    final canvasSize = _lastCanvasSize;
    if (viewportSize == null || canvasSize == null) {
      return;
    }

    final matrix = _controller.value.clone();
    final scale = matrix.getMaxScaleOnAxis();
    final scaledWidth = canvasSize.width * scale;
    final scaledHeight = canvasSize.height * scale;

    double minDx;
    double maxDx;
    if (scaledWidth <= viewportSize.width) {
      final centeredDx = (viewportSize.width - scaledWidth) / 2;
      minDx = centeredDx;
      maxDx = centeredDx;
    } else {
      minDx = viewportSize.width - scaledWidth;
      maxDx = 0;
    }

    double minDy;
    double maxDy;
    if (scaledHeight <= viewportSize.height) {
      final centeredDy = (viewportSize.height - scaledHeight) / 2;
      minDy = centeredDy;
      maxDy = centeredDy;
    } else {
      minDy = viewportSize.height - scaledHeight;
      maxDy = 0;
    }

    final currentDx = matrix.storage[12];
    final currentDy = matrix.storage[13];
    final clampedDx = currentDx.clamp(minDx, maxDx);
    final clampedDy = currentDy.clamp(minDy, maxDy);

    if (clampedDx == currentDx && clampedDy == currentDy) {
      return;
    }

    _isClampingTransform = true;
    matrix.setTranslationRaw(clampedDx, clampedDy, 0);
    _controller.value = matrix;
    _isClampingTransform = false;
  }

  void _fitToViewport({
    required Size viewportSize,
    required Size canvasSize,
    required String signature,
  }) {
    if (_lastFitSignature == signature ||
        viewportSize.width <= 0 ||
        viewportSize.height <= 0 ||
        canvasSize.width <= 0 ||
        canvasSize.height <= 0) {
      return;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _lastFitSignature == signature) {
        return;
      }

      final scale = math.min(
            viewportSize.width / canvasSize.width,
            viewportSize.height / canvasSize.height,
          ) *
          0.92;
      _fittedScale = scale.clamp(0.1, 4.0);
      final dx = (viewportSize.width - (canvasSize.width * scale)) / 2;
      final dy = (viewportSize.height - (canvasSize.height * scale)) / 2;

      final matrix = Matrix4.diagonal3Values(scale, scale, 1);
      matrix.setTranslationRaw(dx, dy, 0);
      _controller.value = matrix;
      _lastFitSignature = signature;
      _lastViewportSize = viewportSize;
      _lastCanvasSize = canvasSize;
    });
  }

  void _resetView() {
    final viewportSize = _lastViewportSize;
    final canvasSize = _lastCanvasSize;
    if (viewportSize == null || canvasSize == null) {
      return;
    }
    _lastFitSignature = null;
    _fitToViewport(
      viewportSize: viewportSize,
      canvasSize: canvasSize,
      signature:
          '${widget.entities.length}:${widget.relations.length}:${canvasSize.width}:${canvasSize.height}:manual',
    );
  }

  void _adjustZoom(double factor) {
    final current = _controller.value;
    final currentScale = current.getMaxScaleOnAxis();
    final nextScale = (currentScale * factor).clamp(_fittedScale, 2.8);
    final ratio = nextScale / currentScale;
    final matrix = Matrix4.copy(current);
    matrix.scaleByDouble(ratio, ratio, 1, 1);
    _controller.value = matrix;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final width =
            constraints.maxWidth.isFinite ? constraints.maxWidth : 960.0;
        final height = math.max(680.0, width * 0.72);
        final layoutSignature =
            '${_signatureForEntities(widget.entities)}:${_signatureForRelations(widget.relations)}:${width.toStringAsFixed(1)}:${height.toStringAsFixed(1)}';
        if (_cachedLayout == null ||
            _cachedLayoutSignature != layoutSignature) {
          _cachedLayout = GraphLayout.build(
            viewportWidth: width,
            viewportHeight: height,
            entities: widget.entities,
            relations: widget.relations,
          );
          _cachedLayoutSignature = layoutSignature;
        }
        final layout = _cachedLayout!;
        _activeRelation ??=
            widget.relations.isNotEmpty ? widget.relations.first : null;
        final fitSignature =
            '${widget.entities.length}:${widget.relations.length}:${layout.canvasSize.width}:${layout.canvasSize.height}';
        _fitToViewport(
          viewportSize: Size(width, height - 44),
          canvasSize: layout.canvasSize,
          signature: fitSignature,
        );

        if (layout.nodes.isEmpty) {
          return Container(
            height: 420,
            decoration: BoxDecoration(
              color: const Color(0xFFF6F4EE),
              borderRadius: BorderRadius.circular(20),
            ),
            alignment: Alignment.center,
            child: const Text('No graph elements match the current filters.'),
          );
        }

        return Container(
          height: height,
          decoration: BoxDecoration(
            color: const Color(0xFFF6F4EE),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: const Color(0xFFDAD2C5)),
          ),
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(
                  children: [
                    Icon(Icons.open_with,
                        size: 18, color: theme.colorScheme.primary),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'The graph auto-fits on load. Drag to pan. Pinch or scroll to zoom. Hover an edge to reveal its label, then click for source evidence.',
                        style: TextStyle(fontSize: 13),
                      ),
                    ),
                    const SizedBox(width: 12),
                    OutlinedButton(
                      onPressed: () => _adjustZoom(0.9),
                      child: const Text('Smaller'),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton(
                      onPressed: _resetView,
                      child: const Text('Reset View'),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton(
                      onPressed: () => _adjustZoom(1.1),
                      child: const Text('Larger'),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: InteractiveViewer(
                  transformationController: _controller,
                  minScale: _fittedScale,
                  maxScale: 2.8,
                  boundaryMargin: EdgeInsets.zero,
                  panEnabled: _draggingNodeId == null,
                  scaleEnabled: _draggingNodeId == null,
                  child: Center(
                    child: SizedBox(
                      width: layout.canvasSize.width,
                      height: layout.canvasSize.height,
                      child: Stack(
                        children: [
                          Positioned.fill(
                            child: Listener(
                              onPointerDown: (event) {
                                final node = layout.nodeAt(event.localPosition);
                                if (node == null) {
                                  return;
                                }
                                final connectedIds = layout.getConnectedNodeIds(node.entity.id);
                                final connectedOffsets = <String, Offset>{};
                                for (final connectedId in connectedIds) {
                                  final connectedNode = layout.nodes.firstWhere(
                                    (n) => n.entity.id == connectedId,
                                  );
                                  connectedOffsets[connectedId] = connectedNode.center - node.center;
                                }
                                setState(() {
                                  _draggingNodeId = node.entity.id;
                                  _dragPointer = event.pointer;
                                  _dragOffset =
                                      event.localPosition - node.center;
                                  _connectedNodeOffsets = connectedOffsets;
                                });
                                widget.onHover(entity: node.entity);
                              },
                              onPointerMove: (event) {
                                if (_draggingNodeId == null ||
                                    _dragPointer != event.pointer ||
                                    _dragOffset == null ||
                                    _cachedLayout == null) {
                                  return;
                                }
                                final target =
                                    event.localPosition - _dragOffset!;
                                setState(() {
                                  _cachedLayout = _cachedLayout!.moveNodeWithConnected(
                                    _draggingNodeId!,
                                    target,
                                    _connectedNodeOffsets,
                                  );
                                  _activeRelation = null;
                                });
                              },
                              onPointerUp: (event) {
                                if (_dragPointer == event.pointer) {
                                  setState(() {
                                    _draggingNodeId = null;
                                    _dragPointer = null;
                                    _dragOffset = null;
                                    _connectedNodeOffsets = {};
                                  });
                                }
                              },
                              onPointerCancel: (event) {
                                if (_dragPointer == event.pointer) {
                                  setState(() {
                                    _draggingNodeId = null;
                                    _dragPointer = null;
                                    _dragOffset = null;
                                    _connectedNodeOffsets = {};
                                  });
                                }
                              },
                              child: MouseRegion(
                                cursor: _draggingNodeId == null
                                    ? SystemMouseCursors.grab
                                    : SystemMouseCursors.grabbing,
                                onExit: (_) {
                                  widget.onHover();
                                  if (_draggingNodeId == null) {
                                    setState(() {
                                      _activeRelation = null;
                                    });
                                  }
                                },
                                onHover: (event) {
                                  if (_draggingNodeId != null) {
                                    return;
                                  }
                                  final pos = event.localPosition;
                                  if (pos.dx < 0 || pos.dy < 0 ||
                                      pos.dx > layout.canvasSize.width ||
                                      pos.dy > layout.canvasSize.height) {
                                    widget.onHover();
                                    setState(() {
                                      _activeRelation = null;
                                    });
                                    return;
                                  }
                                  final hoveredNode = layout.nodeAt(pos);
                                  final hoveredEdge = layout.edgeAt(pos);
                                  if (_activeRelation?.id !=
                                      hoveredEdge?.relation.id) {
                                    setState(() {
                                      _activeRelation = hoveredEdge?.relation;
                                    });
                                  }
                                  widget.onHover(
                                    entity: hoveredNode?.entity,
                                    relation: hoveredEdge?.relation,
                                  );
                                },
                                child: GestureDetector(
                                  behavior: HitTestBehavior.opaque,
                                  onTapUp: (details) {
                                    if (_draggingNodeId != null) {
                                      return;
                                    }
                                    final tappedNode =
                                        layout.nodeAt(details.localPosition);
                                    if (tappedNode != null) {
                                      widget.onSelectEntity(tappedNode.entity);
                                      return;
                                    }
                                    final tappedEdge =
                                        layout.edgeAt(details.localPosition);
                                    if (tappedEdge != null) {
                                      setState(() {
                                        _activeRelation = tappedEdge.relation;
                                      });
                                      widget.onSelectRelation(
                                        tappedEdge.relation,
                                      );
                                    }
                                  },
                                  child: CustomPaint(
                                    painter: GraphPainter(
                                      nodes: layout.nodes,
                                      edges: layout.edges,
                                      theme: theme,
                                      canvasSize: layout.canvasSize,
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                          if (_activeRelation != null &&
                              layout.edgeByRelationId
                                  .containsKey(_activeRelation!.id))
                            Positioned(
                              left: layout
                                      .edgeByRelationId[_activeRelation!.id]!
                                      .midpoint
                                      .dx -
                                  58,
                              top: layout.edgeByRelationId[_activeRelation!.id]!
                                      .midpoint.dy -
                                  14,
                              width: 116,
                              height: 28,
                              child: IgnorePointer(
                                child: Center(
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 8,
                                      vertical: 4,
                                    ),
                                    decoration: BoxDecoration(
                                      color:
                                          Colors.white.withValues(alpha: 0.94),
                                      borderRadius: BorderRadius.circular(999),
                                      border: Border.all(
                                        color: predicateColor(
                                            _activeRelation!.predicate),
                                      ),
                                    ),
                                    child: Text(
                                      _activeRelation!.predicate,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _LegendChip extends StatelessWidget {
  const _LegendChip({required this.type});

  final String type;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: entityTypeColor(type),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        type,
        style: const TextStyle(
          color: Color(0xFF102D22),
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _EntityPanel extends StatelessWidget {
  const _EntityPanel({required this.entity});

  final EntityModel entity;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Entity Detail',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Text(entity.name, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 8),
            Text('Type: ${entity.type}'),
            Text('Source document: ${entity.sourceDoc}'),
            const SizedBox(height: 16),
            Text('Mentions', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            ...entity.mentions.map(
              (mention) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  '${mention.docId} • chars ${mention.charStart}-${mention.charEnd}',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HoverEntityPanel extends StatelessWidget {
  const _HoverEntityPanel({required this.entity});

  final EntityModel entity;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Hovered Node', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Text(entity.name, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('${entity.type} • ${entity.sourceDoc}'),
            const SizedBox(height: 12),
            const Text('Click the node to fetch mentions and full detail.'),
          ],
        ),
      ),
    );
  }
}

class _HoverRelationPanel extends StatelessWidget {
  const _HoverRelationPanel({required this.relation});

  final RelationModel relation;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Hovered Edge', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Text(
              '${relation.subject}  ${relation.predicate}  ${relation.object}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text('Document: ${relation.sourceDoc}'),
            Text('Confidence: ${relation.confidence.toStringAsFixed(2)}'),
            const SizedBox(height: 12),
            const Text('Click the edge label to load highlighted evidence.'),
          ],
        ),
      ),
    );
  }
}

class _EvidencePanel extends StatelessWidget {
  const _EvidencePanel({required this.evidence});

  final RelationEvidence evidence;

  @override
  Widget build(BuildContext context) {
    final chunk = evidence.chunk;
    final localStart = (evidence.highlight.charStart - chunk.charStart)
        .clamp(0, chunk.text.length)
        .toInt();
    final localEnd = (evidence.highlight.charEnd - chunk.charStart)
        .clamp(0, chunk.text.length)
        .toInt();
    final before = chunk.text.substring(0, localStart);
    final highlight = chunk.text.substring(localStart, localEnd);
    final after = chunk.text.substring(localEnd);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Evidence Detail',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Text(
              '${evidence.relation.subject}  ${evidence.relation.predicate}  ${evidence.relation.object}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text('Document: ${evidence.document.title}'),
            Text('Chunk: ${chunk.id} (${chunk.charStart}-${chunk.charEnd})'),
            Text(
                'Highlight: ${evidence.highlight.charStart}-${evidence.highlight.charEnd}'),
            const SizedBox(height: 16),
            Text('Evidence text',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            SelectableText.rich(
              TextSpan(
                style: Theme.of(context).textTheme.bodyMedium,
                children: [
                  TextSpan(text: before),
                  TextSpan(
                    text: highlight,
                    style: const TextStyle(
                      backgroundColor: Color(0xFFFFE082),
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  TextSpan(text: after),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PlaceholderDetail extends StatelessWidget {
  const _PlaceholderDetail();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Detail Pane', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            const Text(
              'Hover graph elements for quick context. Click a node for entity detail or click an edge label for highlighted evidence.',
            ),
          ],
        ),
      ),
    );
  }
}

class _DetailPane extends StatelessWidget {
  const _DetailPane({
    required this.selectedEntity,
    required this.selectedEvidence,
    required this.hoveredEntity,
    required this.hoveredRelation,
  });

  final EntityModel? selectedEntity;
  final RelationEvidence? selectedEvidence;
  final ValueNotifier<EntityModel?> hoveredEntity;
  final ValueNotifier<RelationModel?> hoveredRelation;

  @override
  Widget build(BuildContext context) {
    if (selectedEvidence != null) {
      return _EvidencePanel(evidence: selectedEvidence!);
    }
    if (selectedEntity != null) {
      return _EntityPanel(entity: selectedEntity!);
    }

    return AnimatedBuilder(
      animation: Listenable.merge([hoveredEntity, hoveredRelation]),
      builder: (context, _) {
        if (hoveredRelation.value != null) {
          return _HoverRelationPanel(relation: hoveredRelation.value!);
        }
        if (hoveredEntity.value != null) {
          return _HoverEntityPanel(entity: hoveredEntity.value!);
        }
        return const _PlaceholderDetail();
      },
    );
  }
}

class GraphPainter extends CustomPainter {
  GraphPainter({
    required this.nodes,
    required this.edges,
    required this.theme,
    required this.canvasSize,
  });

  final List<GraphNode> nodes;
  final List<GraphEdge> edges;
  final ThemeData theme;
  final Size canvasSize;

  @override
  void paint(Canvas canvas, Size size) {
    final backgroundPaint = Paint()
      ..color = const Color(0xFFEDE6D8)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    const dotGap = 48.0;
    for (double x = 24; x < canvasSize.width; x += dotGap) {
      for (double y = 24; y < canvasSize.height; y += dotGap) {
        canvas.drawCircle(Offset(x, y), 1.1, backgroundPaint);
      }
    }

    for (final edge in edges) {
      final paint = Paint()
        ..color = edge.color.withValues(alpha: 0.45)
        ..strokeWidth = 2 + (edge.relation.confidence * 2.5)
        ..style = PaintingStyle.stroke;
      canvas.drawLine(edge.from, edge.to, paint);
    }

    for (final node in nodes) {
      final fill = Paint()
        ..color = entityTypeColor(node.entity.type)
        ..style = PaintingStyle.fill;
      final border = Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2;
      final shadow = Paint()
        ..color = const Color(0x22000000)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);

      canvas.drawCircle(node.center.translate(0, 4), node.radius, shadow);
      canvas.drawCircle(node.center, node.radius, fill);
      canvas.drawCircle(node.center, node.radius, border);

      if (node.showLabel) {
        final textPainter = TextPainter(
          text: TextSpan(
            text: shortEntityLabel(node.entity.name),
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: Color(0xFF102D22),
            ),
          ),
          textAlign: TextAlign.center,
          textDirection: TextDirection.ltr,
          maxLines: 2,
          ellipsis: '…',
        )..layout(maxWidth: node.radius * 1.6);

        textPainter.paint(
          canvas,
          Offset(
            node.center.dx - (textPainter.width / 2),
            node.center.dy - (textPainter.height / 2),
          ),
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant GraphPainter oldDelegate) {
    return oldDelegate.edges != edges || oldDelegate.nodes != nodes;
  }
}

class GraphLayout {
  GraphLayout({
    required this.nodes,
    required this.edges,
    required this.canvasSize,
  });

  final List<GraphNode> nodes;
  final List<GraphEdge> edges;
  final Size canvasSize;

  Map<String, GraphEdge> get edgeByRelationId => {
        for (final edge in edges) edge.relation.id: edge,
      };

  factory GraphLayout.build({
    required double viewportWidth,
    required double viewportHeight,
    required List<EntityModel> entities,
    required List<RelationModel> relations,
  }) {
    final entityById = {for (final entity in entities) entity.id: entity};
    final nodes = <GraphNode>[];
    final positions = <String, Offset>{};
    final velocities = <String, Offset>{};
    final degree = <String, int>{};

    for (final entity in entities) {
      degree[entity.id] = 0;
    }
    for (final relation in relations) {
      degree[relation.subject] = (degree[relation.subject] ?? 0) + 1;
      degree[relation.object] = (degree[relation.object] ?? 0) + 1;
    }

    final canvasWidth = math.max(viewportWidth * 1.18, 1180.0);
    final canvasHeight = math.max(viewportHeight * 1.1, 920.0);
    final center = Offset(canvasWidth / 2, canvasHeight / 2);

    final personEntities =
        entities.where((entity) => entity.type == 'Person').toList()
          ..sort(
            (a, b) => a.name.compareTo(b.name),
          );
    final outerEntities =
        entities.where((entity) => entity.type != 'Person').toList()
          ..sort(
            (a, b) => a.name.compareTo(b.name),
          );

    for (var i = 0; i < personEntities.length; i++) {
      final angle = (2 * math.pi * i) / math.max(1, personEntities.length);
      final radius = 80.0 + (personEntities.length * 4.0);
      positions[personEntities[i].id] = Offset(
        center.dx + math.cos(angle) * radius,
        center.dy + math.sin(angle) * radius,
      );
      velocities[personEntities[i].id] = Offset.zero;
    }

    for (var i = 0; i < outerEntities.length; i++) {
      final entity = outerEntities[i];
      final angle = (2 * math.pi * i) / math.max(1, outerEntities.length);
      final radius = switch (entity.type) {
        'Time' => 250.0,
        'Place' => 220.0,
        'Organization' => 210.0,
        'Work' => 230.0,
        _ => 235.0,
      };
      positions[entity.id] = Offset(
        center.dx + math.cos(angle) * radius,
        center.dy + math.sin(angle) * radius,
      );
      velocities[entity.id] = Offset.zero;
    }

    for (var iteration = 0; iteration < 220; iteration++) {
      final forces = <String, Offset>{
        for (final entity in entities) entity.id: Offset.zero,
      };

      for (var i = 0; i < entities.length; i++) {
        for (var j = i + 1; j < entities.length; j++) {
          final a = entities[i];
          final b = entities[j];
          final pa = positions[a.id]!;
          final pb = positions[b.id]!;
          final dx = pa.dx - pb.dx;
          final dy = pa.dy - pb.dy;
          final distSq = math.max(900.0, (dx * dx) + (dy * dy));
          final dist = math.sqrt(distSq);
          final repulsion = 6800 / distSq;
          final fx = (dx / dist) * repulsion;
          final fy = (dy / dist) * repulsion;
          forces[a.id] = forces[a.id]! + Offset(fx, fy);
          forces[b.id] = forces[b.id]! - Offset(fx, fy);
        }
      }

      for (final relation in relations) {
        final from = positions[relation.subject]!;
        final to = positions[relation.object]!;
        final delta = to - from;
        final distance = math.max(1.0, delta.distance);
        final ideal = entityById[relation.object]?.type == 'Time' ? 74.0 : 96.0;
        final attraction = (distance - ideal) * 0.0055;
        final vector = Offset(
          (delta.dx / distance) * attraction,
          (delta.dy / distance) * attraction,
        );
        forces[relation.subject] = forces[relation.subject]! + vector;
        forces[relation.object] = forces[relation.object]! - vector;
      }

      for (final entity in entities) {
        final current = positions[entity.id]!;
        final toCenter = center - current;
        final distance = math.max(1.0, toCenter.distance);
        final preferredRadius = switch (entity.type) {
          'Person' => 65.0 + ((degree[entity.id] ?? 0) * 6.0),
          'Place' => 170.0,
          'Organization' => 185.0,
          'Work' => 210.0,
          'Time' => 245.0,
          _ => 220.0,
        };
        final radialError = distance - preferredRadius;
        final radialPull = radialError * 0.0038;
        final centerForce = Offset(
          (toCenter.dx / distance) * radialPull,
          (toCenter.dy / distance) * radialPull,
        );
        forces[entity.id] = forces[entity.id]! + centerForce;

        if (entity.type == 'Person') {
          forces[entity.id] = forces[entity.id]! +
              Offset(
                (center.dx - current.dx) * 0.0015,
                (center.dy - current.dy) * 0.0015,
              );
        }
      }

      for (final entity in entities) {
        final velocity = velocities[entity.id]!;
        final nextVelocity = Offset(
          (velocity.dx + forces[entity.id]!.dx) * 0.92,
          (velocity.dy + forces[entity.id]!.dy) * 0.92,
        );
        velocities[entity.id] = nextVelocity;

        final current = positions[entity.id]!;
        positions[entity.id] = Offset(
          (current.dx + nextVelocity.dx).clamp(48.0, canvasWidth - 48.0),
          (current.dy + nextVelocity.dy).clamp(48.0, canvasHeight - 48.0),
        );
      }
    }

    for (final entity in entities) {
      nodes.add(
        GraphNode(
          entity: entity,
          center: positions[entity.id]!,
          radius: entity.type == 'Person' ? 28 : 14,
          showLabel: entity.type == 'Person',
        ),
      );
    }

    final edges = <GraphEdge>[];
    for (final relation in relations) {
      final from = positions[relation.subject];
      final to = positions[relation.object];
      final subject = entityById[relation.subject];
      final object = entityById[relation.object];
      if (from == null || to == null || subject == null || object == null) {
        continue;
      }
      edges.add(
        GraphEdge(
          relation: relation,
          from: from,
          to: to,
          color: predicateColor(relation.predicate),
        ),
      );
    }

    return GraphLayout(
      nodes: nodes,
      edges: edges,
      canvasSize: Size(canvasWidth, canvasHeight),
    );
  }

  GraphEdge? edgeAt(Offset position) {
    for (final edge in edges) {
      if (_distanceToSegment(position, edge.from, edge.to) <= 14) {
        return edge;
      }
    }
    return null;
  }

  GraphNode? nodeAt(Offset position) {
    for (final node in nodes.reversed) {
      if ((position - node.center).distance <= node.radius + 4) {
        return node;
      }
    }
    return null;
  }

  Set<String> getConnectedNodeIds(String nodeId) {
    final connected = <String>{};
    for (final edge in edges) {
      if (edge.relation.subject == nodeId) {
        connected.add(edge.relation.object);
      } else if (edge.relation.object == nodeId) {
        connected.add(edge.relation.subject);
      }
    }
    return connected;
  }

  GraphLayout moveNode(String nodeId, Offset rawCenter) {
    final node = nodes.firstWhere(
      (item) => item.entity.id == nodeId,
      orElse: () => throw StateError('node not found: $nodeId'),
    );
    final clampedCenter = Offset(
      rawCenter.dx.clamp(node.radius + 8, canvasSize.width - node.radius - 8),
      rawCenter.dy.clamp(node.radius + 8, canvasSize.height - node.radius - 8),
    );

    final updatedNodes = nodes
        .map(
          (item) => item.entity.id == nodeId
              ? item.copyWith(center: clampedCenter)
              : item,
        )
        .toList();

    final updatedEdges = edges.map((edge) {
      final from = edge.relation.subject == nodeId ? clampedCenter : edge.from;
      final to = edge.relation.object == nodeId ? clampedCenter : edge.to;
      return GraphEdge(
        relation: edge.relation,
        from: from,
        to: to,
        color: edge.color,
      );
    }).toList();

    return GraphLayout(
      nodes: updatedNodes,
      edges: updatedEdges,
      canvasSize: canvasSize,
    );
  }

  GraphLayout moveNodeWithConnected(
    String nodeId,
    Offset rawCenter,
    Map<String, Offset> connectedOffsets,
  ) {
    final node = nodes.firstWhere(
      (item) => item.entity.id == nodeId,
      orElse: () => throw StateError('node not found: $nodeId'),
    );
    final clampedCenter = Offset(
      rawCenter.dx.clamp(node.radius + 8, canvasSize.width - node.radius - 8),
      rawCenter.dy.clamp(node.radius + 8, canvasSize.height - node.radius - 8),
    );

    final newPositions = <String, Offset>{nodeId: clampedCenter};

    for (final entry in connectedOffsets.entries) {
      final connectedId = entry.key;
      final relativeOffset = entry.value;
      final connectedNode = nodes.firstWhere(
        (item) => item.entity.id == connectedId,
        orElse: () => throw StateError('connected node not found: $connectedId'),
      );
      final newCenter = clampedCenter + relativeOffset;
      final clampedConnectedCenter = Offset(
        newCenter.dx.clamp(connectedNode.radius + 8, canvasSize.width - connectedNode.radius - 8),
        newCenter.dy.clamp(connectedNode.radius + 8, canvasSize.height - connectedNode.radius - 8),
      );
      newPositions[connectedId] = clampedConnectedCenter;
    }

    final updatedNodes = nodes
        .map(
          (item) => newPositions.containsKey(item.entity.id)
              ? item.copyWith(center: newPositions[item.entity.id]!)
              : item,
        )
        .toList();

    final updatedEdges = edges.map((edge) {
      final from = newPositions[edge.relation.subject] ?? edge.from;
      final to = newPositions[edge.relation.object] ?? edge.to;
      return GraphEdge(
        relation: edge.relation,
        from: from,
        to: to,
        color: edge.color,
      );
    }).toList();

    return GraphLayout(
      nodes: updatedNodes,
      edges: updatedEdges,
      canvasSize: canvasSize,
    );
  }

  double _distanceToSegment(Offset p, Offset a, Offset b) {
    final dx = b.dx - a.dx;
    final dy = b.dy - a.dy;
    if (dx == 0 && dy == 0) {
      return (p - a).distance;
    }
    final t =
        (((p.dx - a.dx) * dx) + ((p.dy - a.dy) * dy)) / ((dx * dx) + (dy * dy));
    final clampedT = t.clamp(0.0, 1.0);
    final projection = Offset(a.dx + (dx * clampedT), a.dy + (dy * clampedT));
    return (p - projection).distance;
  }
}

class GraphNode {
  GraphNode({
    required this.entity,
    required this.center,
    required this.radius,
    required this.showLabel,
  });

  final EntityModel entity;
  final Offset center;
  final double radius;
  final bool showLabel;

  GraphNode copyWith({
    Offset? center,
  }) {
    return GraphNode(
      entity: entity,
      center: center ?? this.center,
      radius: radius,
      showLabel: showLabel,
    );
  }
}

class GraphEdge {
  GraphEdge({
    required this.relation,
    required this.from,
    required this.to,
    required this.color,
  });

  final RelationModel relation;
  final Offset from;
  final Offset to;
  final Color color;

  Offset get midpoint => Offset((from.dx + to.dx) / 2, (from.dy + to.dy) / 2);
}

Color entityTypeColor(String type) {
  switch (type) {
    case 'Person':
      return const Color(0xFFCFE8D8);
    case 'Place':
      return const Color(0xFFF0D9B5);
    case 'Time':
      return const Color(0xFFF4E7A1);
    case 'Organization':
      return const Color(0xFFD6E4F0);
    case 'Work':
      return const Color(0xFFE7D8F3);
    default:
      return const Color(0xFFE4E0D7);
  }
}

Color predicateColor(String predicate) {
  final hash = predicate.codeUnits.fold<int>(0, (sum, value) => sum + value);
  final colors = [
    const Color(0xFF0B6E4F),
    const Color(0xFF8F5E15),
    const Color(0xFF476C9B),
    const Color(0xFF914E89),
    const Color(0xFF7B3F00),
  ];
  return colors[hash % colors.length];
}

String shortEntityLabel(String value) {
  final words =
      value.split(RegExp(r'\s+')).where((item) => item.isNotEmpty).toList();
  if (words.length >= 2) {
    return '${words.first}\n${words[1]}';
  }
  return value.length > 16 ? '${value.substring(0, 14)}…' : value;
}

int _signatureForEntities(List<EntityModel> entities) {
  return entities.fold<int>(
    entities.length,
    (hash, entity) =>
        Object.hash(hash, entity.id, entity.type, entity.sourceDoc),
  );
}

int _signatureForRelations(List<RelationModel> relations) {
  return relations.fold<int>(
    relations.length,
    (hash, relation) => Object.hash(
      hash,
      relation.id,
      relation.subject,
      relation.predicate,
      relation.object,
    ),
  );
}

class Doc2GraphApi {
  Future<JobResponse> createWikipediaFixtureJob(String baseUrl) async {
    final response =
        await http.post(Uri.parse('$baseUrl/api/v1/dev/fixtures/wikipedia'));
    return _decodeResponse(response, JobResponse.fromJson);
  }

  Future<GraphData> fetchGraph(String baseUrl, String jobId) async {
    final response =
        await http.get(Uri.parse('$baseUrl/api/v1/graph?job_id=$jobId'));
    return _decodeResponse(response, GraphData.fromJson);
  }

  Future<EntityModel> fetchEntity(
      String baseUrl, String jobId, String entityId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/v1/entities/$entityId?job_id=$jobId'),
    );
    return _decodeResponse(
      response,
      (json) => EntityModel.fromJson(json['entity'] as Map<String, dynamic>),
    );
  }

  Future<RelationEvidence> fetchRelationEvidence(
    String baseUrl,
    String jobId,
    String relationId,
  ) async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/v1/relations/$relationId/evidence?job_id=$jobId'),
    );
    return _decodeResponse(response, RelationEvidence.fromJson);
  }

  T _decodeResponse<T>(
    http.Response response,
    T Function(Map<String, dynamic> json) parser,
  ) {
    final body = response.body.isEmpty
        ? <String, dynamic>{}
        : jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
          body['error'] ?? 'Request failed with status ${response.statusCode}');
    }
    return parser(body);
  }
}

class JobResponse {
  JobResponse({
    required this.job,
    required this.documents,
  });

  final JobModel job;
  final List<DocumentModel> documents;

  factory JobResponse.fromJson(Map<String, dynamic> json) {
    return JobResponse(
      job: JobModel.fromJson(json['job'] as Map<String, dynamic>),
      documents: ((json['documents'] as List<dynamic>? ?? <dynamic>[]))
          .map((item) => DocumentModel.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class GraphData {
  GraphData({
    required this.documents,
    required this.entities,
    required this.relations,
  });

  final List<DocumentModel> documents;
  final List<EntityModel> entities;
  final List<RelationModel> relations;

  factory GraphData.fromJson(Map<String, dynamic> json) {
    return GraphData(
      documents: ((json['documents'] as List<dynamic>? ?? <dynamic>[]))
          .map((item) => DocumentModel.fromJson(item as Map<String, dynamic>))
          .toList(),
      entities: ((json['entities'] as List<dynamic>? ?? <dynamic>[]))
          .map((item) => EntityModel.fromJson(item as Map<String, dynamic>))
          .toList(),
      relations: ((json['relations'] as List<dynamic>? ?? <dynamic>[]))
          .map((item) => RelationModel.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class JobModel {
  JobModel({
    required this.id,
    required this.status,
  });

  final String id;
  final String status;

  factory JobModel.fromJson(Map<String, dynamic> json) {
    return JobModel(
      id: json['id'] as String? ?? '',
      status: json['status'] as String? ?? '',
    );
  }
}

class DocumentModel {
  DocumentModel({
    required this.id,
    required this.title,
    required this.sourceType,
  });

  final String id;
  final String title;
  final String sourceType;

  factory DocumentModel.fromJson(Map<String, dynamic> json) {
    return DocumentModel(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      sourceType: json['source_type'] as String? ?? '',
    );
  }
}

class EntityModel {
  EntityModel({
    required this.id,
    required this.name,
    required this.type,
    required this.sourceDoc,
    required this.mentions,
  });

  final String id;
  final String name;
  final String type;
  final String sourceDoc;
  final List<MentionModel> mentions;

  factory EntityModel.fromJson(Map<String, dynamic> json) {
    return EntityModel(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      type: json['type'] as String? ?? '',
      sourceDoc: json['source_doc'] as String? ?? '',
      mentions: ((json['mentions'] as List<dynamic>? ?? <dynamic>[]))
          .map((item) => MentionModel.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class RelationModel {
  RelationModel({
    required this.id,
    required this.subject,
    required this.predicate,
    required this.object,
    required this.sourceDoc,
    required this.confidence,
  });

  final String id;
  final String subject;
  final String predicate;
  final String object;
  final String sourceDoc;
  final double confidence;

  factory RelationModel.fromJson(Map<String, dynamic> json) {
    return RelationModel(
      id: json['id'] as String? ?? '',
      subject: json['subject'] as String? ?? '',
      predicate: json['predicate'] as String? ?? '',
      object: json['object'] as String? ?? '',
      sourceDoc: json['source_doc'] as String? ?? '',
      confidence: (json['confidence'] as num? ?? 0).toDouble(),
    );
  }
}

class MentionModel {
  MentionModel({
    required this.docId,
    required this.charStart,
    required this.charEnd,
  });

  final String docId;
  final int charStart;
  final int charEnd;

  factory MentionModel.fromJson(Map<String, dynamic> json) {
    return MentionModel(
      docId: json['doc_id'] as String? ?? '',
      charStart: json['char_start'] as int? ?? 0,
      charEnd: json['char_end'] as int? ?? 0,
    );
  }
}

class RelationEvidence {
  RelationEvidence({
    required this.relation,
    required this.document,
    required this.chunk,
    required this.highlight,
  });

  final RelationModel relation;
  final DocumentModel document;
  final ChunkModel chunk;
  final MentionModel highlight;

  factory RelationEvidence.fromJson(Map<String, dynamic> json) {
    return RelationEvidence(
      relation:
          RelationModel.fromJson(json['relation'] as Map<String, dynamic>),
      document:
          DocumentModel.fromJson(json['document'] as Map<String, dynamic>),
      chunk: ChunkModel.fromJson(json['chunk'] as Map<String, dynamic>),
      highlight:
          MentionModel.fromJson(json['highlight'] as Map<String, dynamic>),
    );
  }
}

class ChunkModel {
  ChunkModel({
    required this.id,
    required this.docId,
    required this.text,
    required this.charStart,
    required this.charEnd,
  });

  final String id;
  final String docId;
  final String text;
  final int charStart;
  final int charEnd;

  factory ChunkModel.fromJson(Map<String, dynamic> json) {
    return ChunkModel(
      id: json['id'] as String? ?? '',
      docId: json['doc_id'] as String? ?? '',
      text: json['text'] as String? ?? '',
      charStart: json['char_start'] as int? ?? 0,
      charEnd: json['char_end'] as int? ?? 0,
    );
  }
}
