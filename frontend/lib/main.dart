import 'dart:convert';
import 'dart:math' as math;

import 'package:file_selector/file_selector.dart';
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
  EntityDetailModel? _selectedEntity;
  RelationEvidence? _selectedEvidence;
  late final ValueNotifier<EntityModel?> _hoveredEntity;
  late final ValueNotifier<RelationModel?> _hoveredRelation;
  double _minConfidence = 0.0;
  String _predicateFilter = 'all';
  final Map<String, EntityDetailModel> _expandedEntityDetails = {};
  List<UploadDocumentDraft> _uploadDrafts = const <UploadDocumentDraft>[];
  List<UploadSelectionIssue> _uploadIssues = const <UploadSelectionIssue>[];
  ProcessingStage _processingStage = ProcessingStage.idle;

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
      _predicateFilter = 'all';
      _expandedEntityDetails.clear();
      _uploadIssues = const <UploadSelectionIssue>[];
      _processingStage = ProcessingStage.extractingGraph;
    });
    _hoveredEntity.value = null;
    _hoveredRelation.value = null;

    try {
      final baseUrl = _normalizedBaseUrl;
      final job = await _api.createWikipediaFixtureJob(baseUrl);
      setState(() {
        _processingStage = ProcessingStage.loadingGraph;
      });
      final graph = await _api.fetchGraph(
        baseUrl,
        job.job.id,
        expandMetadata: false,
      );
      setState(() {
        _job = job;
        _graph = graph;
        _processingStage = ProcessingStage.complete;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
        _processingStage = ProcessingStage.failed;
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _pickMarkdownFiles() async {
    setState(() {
      _error = null;
      _processingStage = ProcessingStage.readingFiles;
    });

    try {
      const markdownGroup = XTypeGroup(
        label: 'Markdown',
        extensions: <String>['md', 'markdown', 'txt'],
      );
      final files = await openFiles(
        acceptedTypeGroups: const <XTypeGroup>[markdownGroup],
      );
      if (files.isEmpty) {
        setState(() {
          _processingStage = _uploadDrafts.isEmpty
              ? ProcessingStage.idle
              : ProcessingStage.readyToBuild;
        });
        return;
      }
      final drafts = <UploadDocumentDraft>[];
      final issues = <UploadSelectionIssue>[];
      if (files.length > 30) {
        issues.add(
          UploadSelectionIssue(
            filename: 'Selection',
            message: 'Choose at most 30 files. You selected ${files.length}.',
          ),
        );
      }

      for (final file in files) {
        final content = await file.readAsString();
        final draft = buildUploadDraft(
          filename: file.name,
          content: content,
          index: drafts.length,
        );
        drafts.add(draft);
        issues.addAll(validateUploadDraft(draft));
      }

      setState(() {
        _uploadDrafts = drafts.take(30).toList();
        _uploadIssues = issues;
        _processingStage = issues.isEmpty
            ? ProcessingStage.readyToBuild
            : ProcessingStage.failed;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
        _processingStage = ProcessingStage.failed;
      });
    }
  }

  Future<void> _runUploadedFiles() async {
    final issues = validateUploadDrafts(_uploadDrafts);
    if (_uploadDrafts.isEmpty || issues.isNotEmpty) {
      setState(() {
        _uploadIssues = issues;
        _error = _uploadDrafts.isEmpty
            ? 'Pick one or more Markdown files before starting a job.'
            : 'Resolve upload validation issues before starting a job.';
        _processingStage = ProcessingStage.failed;
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
      _selectedEntity = null;
      _selectedEvidence = null;
      _predicateFilter = 'all';
      _expandedEntityDetails.clear();
      _uploadIssues = const <UploadSelectionIssue>[];
      _processingStage = ProcessingStage.uploadingDocuments;
    });
    _hoveredEntity.value = null;
    _hoveredRelation.value = null;

    try {
      final baseUrl = _normalizedBaseUrl;
      setState(() {
        _processingStage = ProcessingStage.extractingGraph;
      });
      final job = await _api.createUploadJob(baseUrl, _uploadDrafts);
      setState(() {
        _processingStage = ProcessingStage.loadingGraph;
      });
      final graph = await _api.fetchGraph(
        baseUrl,
        job.job.id,
        expandMetadata: false,
      );
      setState(() {
        _job = job;
        _graph = graph;
        _processingStage = ProcessingStage.complete;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
        _processingStage = ProcessingStage.failed;
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _clearUploadSelection() {
    setState(() {
      _uploadDrafts = const <UploadDocumentDraft>[];
      _uploadIssues = const <UploadSelectionIssue>[];
      _error = null;
      _processingStage = ProcessingStage.idle;
    });
  }

  Future<void> _selectEntity(EntityModel entity) async {
    if (_job == null || _graph == null) {
      return;
    }

    // Toggle: if already expanded, collapse it
    if (_expandedEntityDetails.containsKey(entity.id)) {
      _collapseEntity(entity.id);
      return;
    }

    if (entity.display?.role == 'summary') {
      setState(() {
        _selectedEntity = EntityDetailModel(
          entity: entity,
          hiddenConnections: const <HiddenConnectionModel>[],
          visibleRelationCount: 0,
        );
        _selectedEvidence = null;
      });
      return;
    }

    // Build entity detail from graph data
    final connections = <HiddenConnectionModel>[];
    final entityById = <String, EntityModel>{
      for (final e in _graph!.entities) e.id: e
    };

    // Find all relations where this entity is the subject or object
    for (final relation in _graph!.relations) {
      if (relation.subject == entity.id) {
        final connectedEntity = entityById[relation.object];
        if (connectedEntity != null && connectedEntity.type != 'Person') {
          connections.add(HiddenConnectionModel(
            entity: connectedEntity,
            relation: relation,
            group: connectedEntity.type,
          ));
        }
      } else if (relation.object == entity.id) {
        final connectedEntity = entityById[relation.subject];
        if (connectedEntity != null && connectedEntity.type != 'Person') {
          connections.add(HiddenConnectionModel(
            entity: connectedEntity,
            relation: relation,
            group: connectedEntity.type,
          ));
        }
      }
    }

    // Count visible Person-Person relations
    int visibleRelationCount = 0;
    for (final relation in _graph!.relations) {
      if (relation.subject == entity.id || relation.object == entity.id) {
        final otherEntityId =
            relation.subject == entity.id ? relation.object : relation.subject;
        final otherEntity = entityById[otherEntityId];
        if (otherEntity != null && otherEntity.type == 'Person') {
          visibleRelationCount++;
        }
      }
    }

    final detailedEntity = EntityDetailModel(
      entity: entity,
      hiddenConnections: connections,
      visibleRelationCount: visibleRelationCount,
    );

    setState(() {
      _selectedEntity = detailedEntity;
      _expandedEntityDetails[entity.id] = detailedEntity;
      _selectedEvidence = null;
      _predicateFilter = 'all';
    });
  }

  void _collapseEntity(String entityId) {
    setState(() {
      _expandedEntityDetails.remove(entityId);
      if (_selectedEntity?.entity.id == entityId) {
        _selectedEntity = null;
      }
      _selectedEvidence = null;
      _predicateFilter = 'all';
    });
    _hoveredEntity.value = null;
    _hoveredRelation.value = null;
  }

  void _collapseAllEntities() {
    setState(() {
      _expandedEntityDetails.clear();
      _selectedEntity = null;
      _selectedEvidence = null;
      _predicateFilter = 'all';
    });
    _hoveredEntity.value = null;
    _hoveredRelation.value = null;
  }

  Future<void> _selectRelation(RelationModel relation) async {
    if (_job == null) {
      return;
    }
    if (relation.display?.aggregated == true) {
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

  List<RelationModel> get _displayRelations {
    final graph = _graph;
    if (graph == null) {
      return const <RelationModel>[];
    }

    final relationById = <String, RelationModel>{};
    final majorIds = graph.entities
        .where((entity) => isMajorGraphEntity(entity, graph.documents))
        .map((entity) => entity.id)
        .toSet();

    // Build entity type lookup for performance
    final entityTypeById = <String, String>{
      for (final entity in graph.entities) entity.id: entity.type
    };

    // Get IDs of expanded person entities
    final expandedPersonIds = _expandedEntityDetails.keys.toSet();

    // Show all Person-Person relations (not just major-to-major)
    for (final relation in graph.relations) {
      final subjectType = entityTypeById[relation.subject] ?? '';
      final objectType = entityTypeById[relation.object] ?? '';

      // Show if at least one side is a major entity and it's a Person-Person relation
      if (subjectType == 'Person' && objectType == 'Person') {
        if (majorIds.contains(relation.subject) ||
            majorIds.contains(relation.object)) {
          relationById[relation.id] = relation;
        }
      } else {
        // For Person to non-Person relations, show only if the Person is expanded
        if (subjectType == 'Person' &&
            expandedPersonIds.contains(relation.subject)) {
          relationById[relation.id] = relation;
        } else if (objectType == 'Person' &&
            expandedPersonIds.contains(relation.object)) {
          relationById[relation.id] = relation;
        }
      }
    }

    return relationById.values.toList();
  }

  List<RelationModel> get _filteredRelations {
    final graph = _graph;
    if (graph == null) {
      return const <RelationModel>[];
    }

    // Build entity type lookup for performance
    final entityTypeById = <String, String>{
      for (final entity in graph.entities) entity.id: entity.type
    };

    final relations = _displayRelations;
    final predicateFilter = _effectivePredicateFilter;
    return relations.where((relation) {
      // Always filter by confidence
      if (relation.confidence < _minConfidence) {
        return false;
      }

      // Check if this is a Person-to-Person relation
      final subjectType = entityTypeById[relation.subject] ?? '';
      final objectType = entityTypeById[relation.object] ?? '';
      final isPersonToPersonRelation = subjectType == 'Person' && objectType == 'Person';

      // Person-to-Person relations are always shown (not filtered by predicate)
      // Only filter Person-to-metadata relations by predicate
      if (!isPersonToPersonRelation && predicateFilter != 'all' && relation.predicate != predicateFilter) {
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

    final entityById = <String, EntityModel>{
      for (final entity in graph.entities) entity.id: entity
    };

    final displayEntityIds = <String>{};

    // Always include all major Person entities (document subjects)
    // These should always be visible regardless of filters
    for (final entity in graph.entities) {
      if (entity.type == 'Person' && isMajorGraphEntity(entity, graph.documents)) {
        displayEntityIds.add(entity.id);
      }
    }

    // Use filtered relations to determine which additional entities to show
    // This ensures that when a predicate filter is applied, only relevant metadata entities are shown
    final filteredRelations = _filteredRelations;

    // Collect all entity IDs from filtered relations
    for (final relation in filteredRelations) {
      displayEntityIds.add(relation.subject);
      displayEntityIds.add(relation.object);
    }

    // Filter to only return entities that exist and filter appropriately
    return displayEntityIds
        .map((id) => entityById[id])
        .where((entity) => entity != null && entity.id.isNotEmpty)
        .cast<EntityModel>()
        .toList();
  }

  List<String> get _availablePredicates {
    final graph = _graph;
    if (graph == null) {
      return const ['all'];
    }
    final predicates =
        _displayRelations.map((e) => e.predicate).toSet().toList()..sort();
    return ['all', ...predicates];
  }

  String get _effectivePredicateFilter {
    final predicates = _availablePredicates;
    return effectivePredicateFilter(_predicateFilter, predicates);
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
            uploadDrafts: _uploadDrafts,
            uploadIssues: _uploadIssues,
            processingStage: _processingStage,
            minConfidence: _minConfidence,
            predicateFilter: _effectivePredicateFilter,
            availablePredicates: _availablePredicates,
            expandedEntityCount: _expandedEntityDetails.length,
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
            onCollapseAllEntities: _collapseAllEntities,
            onPickMarkdownFiles: _pickMarkdownFiles,
            onRunUploadedFiles: _runUploadedFiles,
            onClearUploadSelection: _clearUploadSelection,
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
                  onSelectHiddenRelation: _selectRelation,
                  onCollapseEntity: _collapseEntity,
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
                    onSelectHiddenRelation: _selectRelation,
                    onCollapseEntity: _collapseEntity,
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
    required this.uploadDrafts,
    required this.uploadIssues,
    required this.processingStage,
    required this.minConfidence,
    required this.predicateFilter,
    required this.availablePredicates,
    required this.expandedEntityCount,
    required this.onMinConfidenceChanged,
    required this.onPredicateFilterChanged,
    required this.onCollapseAllEntities,
    required this.onPickMarkdownFiles,
    required this.onRunUploadedFiles,
    required this.onClearUploadSelection,
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
  final List<UploadDocumentDraft> uploadDrafts;
  final List<UploadSelectionIssue> uploadIssues;
  final ProcessingStage processingStage;
  final double minConfidence;
  final String predicateFilter;
  final List<String> availablePredicates;
  final int expandedEntityCount;
  final ValueChanged<double> onMinConfidenceChanged;
  final ValueChanged<String> onPredicateFilterChanged;
  final VoidCallback onCollapseAllEntities;
  final Future<void> Function() onPickMarkdownFiles;
  final Future<void> Function() onRunUploadedFiles;
  final VoidCallback onClearUploadSelection;
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
        _UploadPanel(
          baseUrlController: baseUrlController,
          uploadDrafts: uploadDrafts,
          uploadIssues: uploadIssues,
          processingStage: processingStage,
          isLoading: isLoading,
          error: error,
          onPickMarkdownFiles: onPickMarkdownFiles,
          onRunUploadedFiles: onRunUploadedFiles,
          onClearUploadSelection: onClearUploadSelection,
          onRunWikipediaFixtures: onRunWikipediaFixtures,
        ),
        if (job != null) ...[
          const SizedBox(height: 16),
          _JobSummary(
            job: job!,
            entities: filteredEntities.length,
            relations: filteredRelations.length,
            display: graph?.display,
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
                  expandedEntityCount: expandedEntityCount,
                  onMinConfidenceChanged: onMinConfidenceChanged,
                  onPredicateFilterChanged: onPredicateFilterChanged,
                  onCollapseAllEntities: onCollapseAllEntities,
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

class _UploadPanel extends StatelessWidget {
  const _UploadPanel({
    required this.baseUrlController,
    required this.uploadDrafts,
    required this.uploadIssues,
    required this.processingStage,
    required this.isLoading,
    required this.error,
    required this.onPickMarkdownFiles,
    required this.onRunUploadedFiles,
    required this.onClearUploadSelection,
    required this.onRunWikipediaFixtures,
  });

  final TextEditingController baseUrlController;
  final List<UploadDocumentDraft> uploadDrafts;
  final List<UploadSelectionIssue> uploadIssues;
  final ProcessingStage processingStage;
  final bool isLoading;
  final String? error;
  final Future<void> Function() onPickMarkdownFiles;
  final Future<void> Function() onRunUploadedFiles;
  final VoidCallback onClearUploadSelection;
  final Future<void> Function() onRunWikipediaFixtures;

  @override
  Widget build(BuildContext context) {
    final hasBlockingIssues = uploadIssues.isNotEmpty;
    final totalChars =
        uploadDrafts.fold<int>(0, (sum, draft) => sum + draft.content.length);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Documents', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            TextField(
              controller: baseUrlController,
              decoration: const InputDecoration(
                labelText: 'API Base URL',
                hintText: 'http://127.0.0.1:8080',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                FilledButton.icon(
                  onPressed: isLoading ? null : onPickMarkdownFiles,
                  icon: const Icon(Icons.upload_file),
                  label: const Text('Choose Markdown Files'),
                ),
                FilledButton.icon(
                  onPressed:
                      isLoading || uploadDrafts.isEmpty || hasBlockingIssues
                          ? null
                          : onRunUploadedFiles,
                  icon: const Icon(Icons.account_tree),
                  label: const Text('Build Graph From Files'),
                ),
                OutlinedButton.icon(
                  onPressed: isLoading || uploadDrafts.isEmpty
                      ? null
                      : onClearUploadSelection,
                  icon: const Icon(Icons.clear),
                  label: const Text('Clear'),
                ),
                OutlinedButton.icon(
                  onPressed: isLoading ? null : onRunWikipediaFixtures,
                  icon: const Icon(Icons.science),
                  label: const Text('Run Test Fixture'),
                ),
                if (isLoading)
                  const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            _ProcessingStatus(
              stage: processingStage,
              isActive:
                  isLoading || processingStage == ProcessingStage.readingFiles,
            ),
            if (uploadDrafts.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(
                '${uploadDrafts.length} selected files • $totalChars characters',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 8),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 180),
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: uploadDrafts.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final draft = uploadDrafts[index];
                    return ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.description_outlined),
                      title: Text(
                        draft.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(
                        '${draft.filename} • ${draft.content.length} chars',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    );
                  },
                ),
              ),
            ],
            if (uploadIssues.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(
                'Upload Issues',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              ...uploadIssues.map(
                (issue) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.error_outline,
                        size: 18,
                        color: Theme.of(context).colorScheme.error,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '${issue.filename}: ${issue.message}',
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            if (error != null) ...[
              const SizedBox(height: 12),
              Text(
                error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ProcessingStatus extends StatelessWidget {
  const _ProcessingStatus({
    required this.stage,
    required this.isActive,
  });

  final ProcessingStage stage;
  final bool isActive;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                processingStageIcon(stage),
                size: 18,
                color: processingStageColor(stage, colorScheme),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  processingStageLabel(stage),
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          if (processingStageDescription(stage).isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              processingStageDescription(stage),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
          if (isActive) ...[
            const SizedBox(height: 10),
            const LinearProgressIndicator(),
          ],
        ],
      ),
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
    this.display,
  });

  final JobResponse job;
  final int entities;
  final int relations;
  final GraphDisplayModel? display;

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
            if (display != null && display!.transformed)
              _Metric(
                label: 'Hidden Nodes',
                value: '${display!.hiddenEntityCount}',
              ),
            if (display != null && display!.transformed)
              _Metric(
                label: 'Hidden Time',
                value: '${display!.collapsedTimeLeaves}',
              ),
            if (display != null && display!.transformed)
              _Metric(
                label: 'Hidden Place',
                value: '${display!.collapsedPlaceLeaves}',
              ),
            if (display != null && display!.transformed)
              _Metric(
                label: 'Hidden Org',
                value: '${display!.collapsedOrgLeaves}',
              ),
            if (display != null && display!.transformed)
              _Metric(
                label: 'Hidden Edges',
                value: '${display!.hiddenRelationCount}',
              ),
            if (display != null)
              _Metric(
                label: 'Metadata View',
                value: display!.metadataExpanded
                    ? 'Expanded on canvas'
                    : 'Expand on click',
              ),
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
    required this.expandedEntityCount,
    required this.onMinConfidenceChanged,
    required this.onPredicateFilterChanged,
    required this.onCollapseAllEntities,
  });

  final double minConfidence;
  final String predicateFilter;
  final List<String> availablePredicates;
  final int expandedEntityCount;
  final ValueChanged<double> onMinConfidenceChanged;
  final ValueChanged<String> onPredicateFilterChanged;
  final VoidCallback onCollapseAllEntities;

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
        SizedBox(
          width: 320,
          child: Wrap(
            alignment: WrapAlignment.end,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 12,
            runSpacing: 8,
            children: [
              Text(
                'Expanded: $expandedEntityCount',
                overflow: TextOverflow.ellipsis,
              ),
              Tooltip(
                message: 'Collapse all expanded nodes',
                child: OutlinedButton.icon(
                  onPressed:
                      expandedEntityCount == 0 ? null : onCollapseAllEntities,
                  icon: const Icon(Icons.close),
                  label: const Text('Collapse'),
                ),
              ),
            ],
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
  String? _lastBaseSignature;
  Set<String> _lastExpandedEntityIds = {};
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

        // Separate Person entities from expanded metadata entities
        final personEntities =
            widget.entities.where((e) => e.type == 'Person').toList();
        final nonPersonEntities =
            widget.entities.where((e) => e.type != 'Person').toList();
        final currentExpandedEntityIds =
            nonPersonEntities.map((e) => e.id).toSet();

        final baseSignature =
            '${_signatureForEntities(personEntities)}:${width.toStringAsFixed(1)}:${height.toStringAsFixed(1)}';

        // Check if only expanded entities changed (not the base Person network)
        final baseChanged = _lastBaseSignature != baseSignature;
        final onlyExpansionChanged =
            !baseChanged && _lastExpandedEntityIds != currentExpandedEntityIds;

        if (_cachedLayout == null || baseChanged) {
          // Full rebuild - base network changed
          _cachedLayout = GraphLayout.build(
            viewportWidth: width,
            viewportHeight: height,
            entities: widget.entities,
            relations: widget.relations,
          );
          _lastBaseSignature = baseSignature;
          _lastExpandedEntityIds = currentExpandedEntityIds;
        } else if (onlyExpansionChanged) {
          // Incremental update - only expansion changed
          _cachedLayout = _cachedLayout!.updateWithExpansion(
            newEntities: widget.entities,
            newRelations: widget.relations,
            previousExpandedIds: _lastExpandedEntityIds,
            currentExpandedIds: currentExpandedEntityIds,
          );
          _lastExpandedEntityIds = currentExpandedEntityIds;
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
                                final connectedIds =
                                    layout.getConnectedNodeIds(node.entity.id);
                                final connectedOffsets = <String, Offset>{};
                                for (final connectedId in connectedIds) {
                                  final connectedNode = layout.nodes.firstWhere(
                                    (n) => n.entity.id == connectedId,
                                  );
                                  connectedOffsets[connectedId] =
                                      connectedNode.center - node.center;
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
                                  _cachedLayout =
                                      _cachedLayout!.moveNodeWithConnected(
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
                                  if (pos.dx < 0 ||
                                      pos.dy < 0 ||
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
                                      if (tappedNode.entity.display?.role ==
                                          'summary') {
                                        widget.onHover(
                                            entity: tappedNode.entity);
                                        return;
                                      }
                                      widget.onSelectEntity(tappedNode.entity);
                                      return;
                                    }
                                    final tappedEdge =
                                        layout.edgeAt(details.localPosition);
                                    if (tappedEdge != null) {
                                      if (tappedEdge
                                              .relation.display?.aggregated ==
                                          true) {
                                        setState(() {
                                          _activeRelation = tappedEdge.relation;
                                        });
                                        widget.onHover(
                                          relation: tappedEdge.relation,
                                        );
                                        return;
                                      }
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
  const _EntityPanel({
    required this.detail,
    required this.onSelectHiddenRelation,
    required this.onCollapseEntity,
  });

  final EntityDetailModel detail;
  final ValueChanged<RelationModel> onSelectHiddenRelation;
  final ValueChanged<String> onCollapseEntity;

  @override
  Widget build(BuildContext context) {
    final entity = detail.entity;
    final groupedConnections = <String, List<HiddenConnectionModel>>{};
    for (final connection in detail.hiddenConnections) {
      groupedConnections
          .putIfAbsent(connection.entity.type, () => <HiddenConnectionModel>[])
          .add(connection);
    }
    final sortedGroups = groupedConnections.keys.toList()..sort();

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
            Text('Visible graph connections: ${detail.visibleRelationCount}'),
            Text(
                'Hidden small-entity facts: ${detail.hiddenConnections.length}'),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => onCollapseEntity(entity.id),
              icon: const Icon(Icons.unfold_less),
              label: const Text('Collapse this node'),
            ),
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
            if (detail.hiddenConnections.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(
                'Hidden Connected Facts',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              ...sortedGroups.map(
                (group) => _HiddenConnectionGroup(
                  title: group,
                  connections: groupedConnections[group]!,
                  onSelectHiddenRelation: onSelectHiddenRelation,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _HiddenConnectionGroup extends StatelessWidget {
  const _HiddenConnectionGroup({
    required this.title,
    required this.connections,
    required this.onSelectHiddenRelation,
  });

  final String title;
  final List<HiddenConnectionModel> connections;
  final ValueChanged<RelationModel> onSelectHiddenRelation;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: const EdgeInsets.only(bottom: 8),
      title: Text('$title (${connections.length})'),
      subtitle: const Text('Expand to inspect hidden entities and evidence'),
      children: connections
          .map(
            (connection) => ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(connection.entity.name),
              subtitle: Text(
                '${connection.relation.predicate} • ${connection.entity.type}',
              ),
              trailing: TextButton(
                onPressed: () => onSelectHiddenRelation(connection.relation),
                child: const Text('Evidence'),
              ),
            ),
          )
          .toList(),
    );
  }
}

class _HoverEntityPanel extends StatelessWidget {
  const _HoverEntityPanel({required this.entity});

  final EntityModel entity;

  @override
  Widget build(BuildContext context) {
    if (entity.display?.role == 'summary') {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Hovered Node',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              Text(entity.name, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(
                'Grouped ${entity.display?.groupKind ?? 'metadata'} • ${entity.display?.memberRelationIds.length ?? 0} hidden facts',
              ),
            ],
          ),
        ),
      );
    }
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
    if (relation.display?.aggregated == true) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Hovered Edge',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              Text(
                relation.predicate,
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Text(
                'Aggregates ${relation.display?.memberRelationIds.length ?? 0} hidden relations.',
              ),
              const SizedBox(height: 12),
              const Text(
                'Use the Expand metadata toggle to reveal the underlying evidence-bearing edges.',
              ),
            ],
          ),
        ),
      );
    }
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
    required this.onSelectHiddenRelation,
    required this.onCollapseEntity,
  });

  final EntityDetailModel? selectedEntity;
  final RelationEvidence? selectedEvidence;
  final ValueNotifier<EntityModel?> hoveredEntity;
  final ValueNotifier<RelationModel?> hoveredRelation;
  final ValueChanged<RelationModel> onSelectHiddenRelation;
  final ValueChanged<String> onCollapseEntity;

  @override
  Widget build(BuildContext context) {
    if (selectedEvidence != null) {
      return _EvidencePanel(evidence: selectedEvidence!);
    }
    if (selectedEntity != null) {
      return _EntityPanel(
        detail: selectedEntity!,
        onSelectHiddenRelation: onSelectHiddenRelation,
        onCollapseEntity: onCollapseEntity,
      );
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
    final personOvalRadiusX = 72.0 + (personEntities.length * 4.0);
    final personOvalRadiusY = 48.0 + (personEntities.length * 2.4);
    final outerTypeCounts = <String, int>{};
    final outerTypeIndex = <String, int>{};
    for (final entity in outerEntities) {
      outerTypeCounts[entity.type] = (outerTypeCounts[entity.type] ?? 0) + 1;
    }

    for (var i = 0; i < personEntities.length; i++) {
      final angle = (2 * math.pi * i) / math.max(1, personEntities.length);
      positions[personEntities[i].id] = Offset(
        center.dx + math.cos(angle) * personOvalRadiusX,
        center.dy + math.sin(angle) * personOvalRadiusY,
      );
      velocities[personEntities[i].id] = Offset.zero;
    }

    for (var i = 0; i < outerEntities.length; i++) {
      final entity = outerEntities[i];
      final typeIndex = outerTypeIndex[entity.type] ?? 0;
      outerTypeIndex[entity.type] = typeIndex + 1;
      final typeTotal = math.max(1, outerTypeCounts[entity.type] ?? 1);
      final sectorCenter = switch (entity.type) {
        'Time' => -math.pi / 2,
        'Place' => math.pi,
        'Organization' => 0.0,
        'Work' => math.pi / 2,
        'MetaGroup' => -math.pi / 6,
        _ => (2 * math.pi * i) / math.max(1, outerEntities.length),
      };
      final sectorSpread = switch (entity.type) {
        'MetaGroup' => 0.55,
        'Organization' => 1.0,
        'Work' => 0.9,
        'Place' => 0.95,
        'Time' => 0.8,
        _ => 1.1,
      };
      final localT = typeTotal == 1 ? 0.0 : (typeIndex / (typeTotal - 1)) - 0.5;
      final angle = sectorCenter + (localT * sectorSpread);
      final radius = switch (entity.type) {
        'Time' => 155.0,
        'Place' => 145.0,
        'Organization' => 138.0,
        'Work' => 148.0,
        'MetaGroup' => 112.0,
        _ => 150.0,
      };
      positions[entity.id] = Offset(
        center.dx + math.cos(angle) * radius,
        center.dy + math.sin(angle) * (radius * 0.7),
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
          'Person' => 34.0 + ((degree[entity.id] ?? 0) * 4.2),
          'MetaGroup' => 88.0,
          'Place' => 118.0,
          'Organization' => 112.0,
          'Work' => 124.0,
          'Time' => 138.0,
          _ => 125.0,
        };
        final radialError = distance - preferredRadius;
        var centerForce = Offset(
          (toCenter.dx / distance) * (radialError * 0.0068),
          (toCenter.dy / distance) * (radialError * 0.0068),
        );
        forces[entity.id] = forces[entity.id]! + centerForce;

        if (entity.type == 'Person') {
          final dx = current.dx - center.dx;
          final dy = current.dy - center.dy;
          final ellipseDistance = math.sqrt(
            ((dx * dx) / (personOvalRadiusX * personOvalRadiusX)) +
                ((dy * dy) / (personOvalRadiusY * personOvalRadiusY)),
          );
          final normalizedDx = dx / math.max(personOvalRadiusX, 1);
          final normalizedDy = dy / math.max(personOvalRadiusY, 1);
          final normalizedLength = math.max(
              0.001,
              math.sqrt((normalizedDx * normalizedDx) +
                  (normalizedDy * normalizedDy)));
          final ellipsePull = (ellipseDistance - 1.0) * 8.5;
          centerForce = Offset(
            -(normalizedDx / normalizedLength) * ellipsePull,
            -(normalizedDy / normalizedLength) * ellipsePull,
          );
          forces[entity.id] = forces[entity.id]! + centerForce;
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
          radius: switch (entity.type) {
            'Person' => 28,
            'MetaGroup' => 22,
            _ => 14,
          },
          showLabel: entity.type == 'Person' || entity.type == 'MetaGroup',
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

  GraphLayout updateWithExpansion({
    required List<EntityModel> newEntities,
    required List<RelationModel> newRelations,
    required Set<String> previousExpandedIds,
    required Set<String> currentExpandedIds,
  }) {
    // Build map of current positions
    final currentPositions = <String, Offset>{
      for (final node in nodes) node.entity.id: node.center
    };

    // Find added and removed entities
    final addedIds = currentExpandedIds.difference(previousExpandedIds);
    final removedIds = previousExpandedIds.difference(currentExpandedIds);

    // Build entity lookup
    final entityById = {for (final entity in newEntities) entity.id: entity};

    // Position new entities near their connected Person entities
    for (final addedId in addedIds) {
      final entity = entityById[addedId];
      if (entity == null) continue;

      // Find which Person entity this is connected to
      Offset? parentPosition;
      for (final relation in newRelations) {
        if (relation.subject == addedId) {
          final parentEntity = entityById[relation.object];
          if (parentEntity != null && parentEntity.type == 'Person') {
            parentPosition = currentPositions[relation.object];
            break;
          }
        } else if (relation.object == addedId) {
          final parentEntity = entityById[relation.subject];
          if (parentEntity != null && parentEntity.type == 'Person') {
            parentPosition = currentPositions[relation.subject];
            break;
          }
        }
      }

      // Position near parent or at a default position
      if (parentPosition != null) {
        // Place in a circle around the parent
        final angle = (addedId.hashCode % 360) * math.pi / 180;
        final distance = 80.0;
        final newX = (parentPosition.dx + math.cos(angle) * distance)
            .clamp(48.0, canvasSize.width - 48);
        final newY = (parentPosition.dy + math.sin(angle) * distance)
            .clamp(48.0, canvasSize.height - 48);
        currentPositions[addedId] = Offset(newX, newY);
      } else {
        // Default position at canvas center
        currentPositions[addedId] = Offset(
          canvasSize.width / 2,
          canvasSize.height / 2,
        );
      }
    }

    // Remove positions for removed entities
    for (final removedId in removedIds) {
      currentPositions.remove(removedId);
    }

    // Build new nodes list
    final newNodes = <GraphNode>[];
    for (final entity in newEntities) {
      final position = currentPositions[entity.id];
      if (position != null) {
        newNodes.add(
          GraphNode(
            entity: entity,
            center: position,
            radius: switch (entity.type) {
              'Person' => 28,
              'MetaGroup' => 22,
              _ => 14,
            },
            showLabel: entity.type == 'Person' || entity.type == 'MetaGroup',
          ),
        );
      }
    }

    // Build new edges list
    final newEdges = <GraphEdge>[];
    for (final relation in newRelations) {
      final from = currentPositions[relation.subject];
      final to = currentPositions[relation.object];
      final subject = entityById[relation.subject];
      final object = entityById[relation.object];
      if (from != null && to != null && subject != null && object != null) {
        newEdges.add(
          GraphEdge(
            relation: relation,
            from: from,
            to: to,
            color: predicateColor(relation.predicate),
          ),
        );
      }
    }

    return GraphLayout(
      nodes: newNodes,
      edges: newEdges,
      canvasSize: canvasSize,
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
        orElse: () =>
            throw StateError('connected node not found: $connectedId'),
      );
      final newCenter = clampedCenter + relativeOffset;
      final clampedConnectedCenter = Offset(
        newCenter.dx.clamp(connectedNode.radius + 8,
            canvasSize.width - connectedNode.radius - 8),
        newCenter.dy.clamp(connectedNode.radius + 8,
            canvasSize.height - connectedNode.radius - 8),
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
    case 'MetaGroup':
      return const Color(0xFFD8DDD2);
    default:
      return const Color(0xFFE4E0D7);
  }
}

bool isMajorGraphEntity(EntityModel entity, List<DocumentModel> documents) {
  if (entity.type != 'Person') {
    return false;
  }
  final names = {
    normalizeGraphLabel(entity.name),
    ...entity.aliases.map(normalizeGraphLabel),
  };
  for (final mention in entity.mentions) {
    for (final document in documents) {
      if (document.id != mention.docId) {
        continue;
      }
      if (names.contains(normalizeGraphLabel(document.title))) {
        return true;
      }
    }
  }
  return false;
}

String normalizeGraphLabel(String value) {
  return value.toLowerCase().trim().replaceAll(RegExp(r'\s+'), ' ');
}

String effectivePredicateFilter(
  String predicateFilter,
  List<String> availablePredicates,
) {
  return availablePredicates.contains(predicateFilter)
      ? predicateFilter
      : 'all';
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

class Doc2GraphApi {
  Future<JobResponse> createWikipediaFixtureJob(String baseUrl) async {
    final response =
        await http.post(Uri.parse('$baseUrl/api/v1/dev/fixtures/wikipedia'));
    return _decodeResponse(response, JobResponse.fromJson);
  }

  Future<JobResponse> createUploadJob(
    String baseUrl,
    List<UploadDocumentDraft> drafts,
  ) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/v1/jobs'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'documents': drafts.map((draft) => draft.toJson()).toList(),
      }),
    );
    return _decodeResponse(response, JobResponse.fromJson);
  }

  Future<GraphData> fetchGraph(
    String baseUrl,
    String jobId, {
    required bool expandMetadata,
  }) async {
    final response = await http.get(
      Uri.parse(
        '$baseUrl/api/v1/graph?job_id=$jobId&expand_metadata=${expandMetadata ? 'true' : 'false'}',
      ),
    );
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

  Future<EntityDetailModel> fetchEntityDetail(
      String baseUrl, String jobId, String entityId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/v1/entities/$entityId?job_id=$jobId'),
    );
    return _decodeResponse(response, EntityDetailModel.fromJson);
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

class UploadDocumentDraft {
  const UploadDocumentDraft({
    required this.id,
    required this.title,
    required this.filename,
    required this.content,
  });

  final String id;
  final String title;
  final String filename;
  final String content;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'source_type': 'markdown',
      'content': content,
      'uri': filename,
    };
  }
}

class UploadSelectionIssue {
  const UploadSelectionIssue({
    required this.filename,
    required this.message,
  });

  final String filename;
  final String message;
}

enum ProcessingStage {
  idle,
  readingFiles,
  readyToBuild,
  uploadingDocuments,
  extractingGraph,
  loadingGraph,
  complete,
  failed,
}

String processingStageLabel(ProcessingStage stage) {
  return switch (stage) {
    ProcessingStage.idle => 'Select Markdown files',
    ProcessingStage.readingFiles => 'Reading files',
    ProcessingStage.readyToBuild => 'Ready to build',
    ProcessingStage.uploadingDocuments => 'Uploading documents',
    ProcessingStage.extractingGraph => 'Extracting graph',
    ProcessingStage.loadingGraph => 'Loading graph',
    ProcessingStage.complete => 'Complete',
    ProcessingStage.failed => 'Needs attention',
  };
}

String processingStageDescription(ProcessingStage stage) {
  return switch (stage) {
    ProcessingStage.idle =>
      'Choose up to 30 Markdown files or run the test fixture.',
    ProcessingStage.readingFiles =>
      'Reading local files and preparing upload payloads.',
    ProcessingStage.readyToBuild => 'Selected files passed local validation.',
    ProcessingStage.uploadingDocuments =>
      'Sending selected documents to the backend.',
    ProcessingStage.extractingGraph =>
      'The backend is processing documents and extracting relationships.',
    ProcessingStage.loadingGraph =>
      'Fetching the display graph for the completed job.',
    ProcessingStage.complete => 'Graph data is loaded and ready to inspect.',
    ProcessingStage.failed => 'Resolve the issue shown below and try again.',
  };
}

IconData processingStageIcon(ProcessingStage stage) {
  return switch (stage) {
    ProcessingStage.idle => Icons.folder_open,
    ProcessingStage.readingFiles => Icons.file_open,
    ProcessingStage.readyToBuild => Icons.check_circle_outline,
    ProcessingStage.uploadingDocuments => Icons.cloud_upload_outlined,
    ProcessingStage.extractingGraph => Icons.account_tree,
    ProcessingStage.loadingGraph => Icons.sync,
    ProcessingStage.complete => Icons.done_all,
    ProcessingStage.failed => Icons.error_outline,
  };
}

Color processingStageColor(ProcessingStage stage, ColorScheme colorScheme) {
  return switch (stage) {
    ProcessingStage.complete ||
    ProcessingStage.readyToBuild =>
      colorScheme.primary,
    ProcessingStage.failed => colorScheme.error,
    _ => colorScheme.onSurfaceVariant,
  };
}

UploadDocumentDraft buildUploadDraft({
  required String filename,
  required String content,
  required int index,
}) {
  final basename = filename.split(RegExp(r'[/\\]')).last;
  final title = inferMarkdownTitle(basename, content);
  return UploadDocumentDraft(
    id: buildUploadDocumentID(basename, index),
    title: title,
    filename: basename,
    content: content,
  );
}

List<UploadSelectionIssue> validateUploadDrafts(
  List<UploadDocumentDraft> drafts,
) {
  final issues = <UploadSelectionIssue>[];
  if (drafts.length > 30) {
    issues.add(
      UploadSelectionIssue(
        filename: 'Selection',
        message: 'Choose at most 30 files. You selected ${drafts.length}.',
      ),
    );
  }
  for (final draft in drafts) {
    issues.addAll(validateUploadDraft(draft));
  }
  return issues;
}

List<UploadSelectionIssue> validateUploadDraft(UploadDocumentDraft draft) {
  final issues = <UploadSelectionIssue>[];
  if (!isSupportedUploadFilename(draft.filename)) {
    issues.add(
      UploadSelectionIssue(
        filename: draft.filename,
        message: 'Only .md, .markdown, and .txt files are supported.',
      ),
    );
  }
  if (draft.content.trim().isEmpty) {
    issues.add(
      UploadSelectionIssue(
        filename: draft.filename,
        message: 'File is empty.',
      ),
    );
  }
  if (draft.title.trim().isEmpty) {
    issues.add(
      UploadSelectionIssue(
        filename: draft.filename,
        message: 'Could not infer a document title.',
      ),
    );
  }
  return issues;
}

bool isSupportedUploadFilename(String filename) {
  final lower = filename.toLowerCase();
  return lower.endsWith('.md') ||
      lower.endsWith('.markdown') ||
      lower.endsWith('.txt');
}

String inferMarkdownTitle(String filename, String content) {
  for (final line in const LineSplitter().convert(content)) {
    final trimmed = line.trim();
    if (trimmed.startsWith('#')) {
      final title = trimmed.replaceFirst(RegExp(r'^#+\s*'), '').trim();
      if (title.isNotEmpty) {
        return title;
      }
    }
  }
  final withoutExtension = filename.replaceFirst(RegExp(r'\.[^.]+$'), '');
  final normalized = withoutExtension.replaceAll(RegExp(r'[_-]+'), ' ').trim();
  return normalized.isEmpty ? filename : normalized;
}

String buildUploadDocumentID(String filename, int index) {
  final withoutExtension = filename.replaceFirst(RegExp(r'\.[^.]+$'), '');
  final slug = withoutExtension
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
      .replaceAll(RegExp(r'^-+|-+$'), '');
  final suffix = (index + 1).toString().padLeft(3, '0');
  return 'upload-$suffix-${slug.isEmpty ? 'document' : slug}';
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
    required this.display,
  });

  final List<DocumentModel> documents;
  final List<EntityModel> entities;
  final List<RelationModel> relations;
  final GraphDisplayModel display;

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
      display: GraphDisplayModel.fromJson(
        json['display'] as Map<String, dynamic>? ?? <String, dynamic>{},
      ),
    );
  }
}

class GraphDisplayModel {
  GraphDisplayModel({
    required this.transformed,
    required this.metadataExpanded,
    required this.hiddenEntityCount,
    required this.hiddenRelationCount,
    required this.collapsedTimeLeaves,
    required this.collapsedPlaceLeaves,
    required this.collapsedOrgLeaves,
    required this.collapsedWorkLeaves,
    required this.summaryNodeCount,
    required this.summaryEdgeCount,
  });

  final bool transformed;
  final bool metadataExpanded;
  final int hiddenEntityCount;
  final int hiddenRelationCount;
  final int collapsedTimeLeaves;
  final int collapsedPlaceLeaves;
  final int collapsedOrgLeaves;
  final int collapsedWorkLeaves;
  final int summaryNodeCount;
  final int summaryEdgeCount;

  factory GraphDisplayModel.fromJson(Map<String, dynamic> json) {
    return GraphDisplayModel(
      transformed: json['transformed'] as bool? ?? false,
      metadataExpanded: json['metadata_expanded'] as bool? ?? false,
      hiddenEntityCount: json['hidden_entity_count'] as int? ?? 0,
      hiddenRelationCount: json['hidden_relation_count'] as int? ?? 0,
      collapsedTimeLeaves: json['collapsed_time_leaves'] as int? ?? 0,
      collapsedPlaceLeaves: json['collapsed_place_leaves'] as int? ?? 0,
      collapsedOrgLeaves: json['collapsed_org_leaves'] as int? ?? 0,
      collapsedWorkLeaves: json['collapsed_work_leaves'] as int? ?? 0,
      summaryNodeCount: json['summary_node_count'] as int? ?? 0,
      summaryEdgeCount: json['summary_edge_count'] as int? ?? 0,
    );
  }
}

class EntityDetailModel {
  EntityDetailModel({
    required this.entity,
    required this.hiddenConnections,
    required this.visibleRelationCount,
  });

  final EntityModel entity;
  final List<HiddenConnectionModel> hiddenConnections;
  final int visibleRelationCount;

  factory EntityDetailModel.fromJson(Map<String, dynamic> json) {
    return EntityDetailModel(
      entity: EntityModel.fromJson(json['entity'] as Map<String, dynamic>),
      hiddenConnections:
          ((json['hidden_connections'] as List<dynamic>? ?? <dynamic>[]))
              .map(
                (item) => HiddenConnectionModel.fromJson(
                  item as Map<String, dynamic>,
                ),
              )
              .toList(),
      visibleRelationCount: json['visible_relation_count'] as int? ?? 0,
    );
  }
}

class HiddenConnectionModel {
  HiddenConnectionModel({
    required this.entity,
    required this.relation,
    required this.group,
  });

  final EntityModel entity;
  final RelationModel relation;
  final String group;

  factory HiddenConnectionModel.fromJson(Map<String, dynamic> json) {
    final display =
        json['display'] as Map<String, dynamic>? ?? <String, dynamic>{};
    return HiddenConnectionModel(
      entity: EntityModel.fromJson(json['entity'] as Map<String, dynamic>),
      relation: RelationModel.fromJson(
        json['relation'] as Map<String, dynamic>,
      ),
      group: display['group'] as String? ?? '',
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
    this.aliases = const <String>[],
    this.display,
  });

  final String id;
  final String name;
  final String type;
  final String sourceDoc;
  final List<MentionModel> mentions;
  final List<String> aliases;
  final EntityDisplayModel? display;

  factory EntityModel.fromJson(Map<String, dynamic> json) {
    return EntityModel(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      type: json['type'] as String? ?? '',
      sourceDoc: json['source_doc'] as String? ?? '',
      mentions: ((json['mentions'] as List<dynamic>? ?? <dynamic>[]))
          .map((item) => MentionModel.fromJson(item as Map<String, dynamic>))
          .toList(),
      aliases: ((json['aliases'] as List<dynamic>? ?? <dynamic>[]))
          .map((item) => item as String)
          .toList(),
      display: json['display'] == null
          ? null
          : EntityDisplayModel.fromJson(
              json['display'] as Map<String, dynamic>,
            ),
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
    this.display,
  });

  final String id;
  final String subject;
  final String predicate;
  final String object;
  final String sourceDoc;
  final double confidence;
  final RelationDisplayModel? display;

  factory RelationModel.fromJson(Map<String, dynamic> json) {
    return RelationModel(
      id: json['id'] as String? ?? '',
      subject: json['subject'] as String? ?? '',
      predicate: json['predicate'] as String? ?? '',
      object: json['object'] as String? ?? '',
      sourceDoc: json['source_doc'] as String? ?? '',
      confidence: (json['confidence'] as num? ?? 0).toDouble(),
      display: json['display'] == null
          ? null
          : RelationDisplayModel.fromJson(
              json['display'] as Map<String, dynamic>,
            ),
    );
  }
}

class EntityDisplayModel {
  EntityDisplayModel({
    required this.role,
    required this.importance,
    required this.crossDocumentCount,
    required this.hidden,
    required this.hiddenReason,
    required this.groupKind,
    required this.expandable,
    required this.memberEntityIds,
    required this.memberRelationIds,
  });

  final String role;
  final double importance;
  final int crossDocumentCount;
  final bool hidden;
  final String hiddenReason;
  final String groupKind;
  final bool expandable;
  final List<String> memberEntityIds;
  final List<String> memberRelationIds;

  factory EntityDisplayModel.fromJson(Map<String, dynamic> json) {
    return EntityDisplayModel(
      role: json['role'] as String? ?? '',
      importance: (json['importance'] as num? ?? 0).toDouble(),
      crossDocumentCount: json['cross_document_count'] as int? ?? 0,
      hidden: json['hidden'] as bool? ?? false,
      hiddenReason: json['hidden_reason'] as String? ?? '',
      groupKind: json['group_kind'] as String? ?? '',
      expandable: json['expandable'] as bool? ?? false,
      memberEntityIds:
          ((json['member_entity_ids'] as List<dynamic>? ?? <dynamic>[]))
              .map((item) => item as String)
              .toList(),
      memberRelationIds:
          ((json['member_relation_ids'] as List<dynamic>? ?? <dynamic>[]))
              .map((item) => item as String)
              .toList(),
    );
  }
}

class RelationDisplayModel {
  RelationDisplayModel({
    required this.role,
    required this.hidden,
    required this.hiddenReason,
    required this.aggregated,
    required this.memberRelationIds,
  });

  final String role;
  final bool hidden;
  final String hiddenReason;
  final bool aggregated;
  final List<String> memberRelationIds;

  factory RelationDisplayModel.fromJson(Map<String, dynamic> json) {
    return RelationDisplayModel(
      role: json['role'] as String? ?? '',
      hidden: json['hidden'] as bool? ?? false,
      hiddenReason: json['hidden_reason'] as String? ?? '',
      aggregated: json['aggregated'] as bool? ?? false,
      memberRelationIds:
          ((json['member_relation_ids'] as List<dynamic>? ?? <dynamic>[]))
              .map((item) => item as String)
              .toList(),
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
