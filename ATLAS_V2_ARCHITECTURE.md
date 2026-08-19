ATLAS_V2_ARCHITECTURE.md
# ATLAS V2 — Architecture Specification

**Document:** `ATLAS_V2_ARCHITECTURE.md`  
**Status:** FROZEN  
**Version:** 1.0  
**Date:** 2026-08-19  
**Product:** Atlas V2 — Laboratório de Viabilidade Física de Terrenos

---

# 1. Document Status

This document defines the frozen architecture for Atlas V2.

The architecture is considered complete and implementation-ready.

The purpose of this document is to:

- define the V2 domain model;
- define ownership and identity rules;
- define persistence boundaries;
- define frontend/backend responsibilities;
- define the simulation contract;
- define the scenario isolation model;
- define the migration strategy from V1;
- prevent architectural drift during implementation.

## Freeze Rule

After this document is frozen:

- architectural decisions marked `FROZEN` MUST NOT be reopened during Phase 1;
- implementation details MAY evolve;
- bugs MAY be fixed;
- factual incompatibilities discovered during the Phase 0 V1 audit MAY require targeted architectural adjustments;
- such adjustments MUST solve a factual incompatibility with V1 and MUST NOT be used to reopen already-settled design preferences.

The next step after this document is:

1. Phase 0 — V1 Audit
2. Phase 1 — Workspace Foundation

---

# 2. Product Definition

Atlas V2 is a persistent workspace for evaluating the physical feasibility of interventions on land.

The core product lifecycle is:

```text
KNOW
  ↓
DESIGN
  ↓
SIMULATE
  ↓
COMPARE
  ↓
VISUALIZE
  ↓
DECIDE
V2 is not a rewrite of the existing physical engines.
Existing validated V1 engines are preserved and integrated through adapters.
V2 provides:
- persistent projects;
- editable project objects;
- geographic context;
- isolated scenarios;
- simulation execution;
- normalized simulation results;
- visualization;
- future What-If analysis;
- incremental migration of existing engines.
3. Architectural Principles
The following principles are mandatory.
3.1 Persistent Workspace
A Project is persistent.
The user must be able to:
create project
→ close application
→ reopen later
→ continue working
Therefore SQLite is part of Phase 1.
Browser-only persistence is NOT the final architecture.
3.2 Flat Project Object Model
There is one generic ProjectObject model.
Objects are distinguished by:
type
There are no subclasses such as:
PondObject
PlatformObject
AccessObject
ZoneObject
Semantic information belongs to the Type Registry.
3.3 Configuration Over Class Hierarchy
Object semantics are defined by the Type Registry.
The registry determines:
- valid geometry types;
- parameter schema;
- rendering style;
- supported engines;
- semantic category;
- terrain modification capability;
- containment policy.
This avoids class hierarchy and distributed type-specific logic.
3.4 Immutable Base Reference
BaseParcel is immutable during normal project editing.
It represents the physical reference parcel against which project objects and scenarios are evaluated.
Scenarios do not modify the BaseParcel.
3.5 Scenario Isolation
Scenarios are isolated snapshots.
A ScenarioObject is a copy of a ProjectObject at a point in time.
There is no automatic synchronization.
Editing the ProjectObject MUST NOT modify existing ScenarioObjects.
3.6 Derived Simulation Results
Simulation results are derived data.
They can be recalculated.
Only the latest result for a given:
scenario_object_id + engine_type
is persisted.
Historical simulation execution history is deferred.
3.7 Existing Engines Are Preserved
Existing V1 physical engines are not rewritten unless the Phase 0 audit proves that adaptation is impossible or unsafe.
V2 integrates them through EngineAdapter.
3.8 CRS Preservation
The existing TM06 / EPSG:3763 transformation is a critical dependency.
It MUST NOT be changed during V2 migration.
The Phase 0 audit must identify all existing uses of the transformation.
3.9 Single Frontend State Boundary
The ProjectStore is the only frontend communication boundary with the backend.
UI components MUST NOT perform direct backend fetches.
All backend communication passes through the Store.
4. Scope of V2
V2 includes:
- persistent Projects;
- BaseParcel;
- ProjectObjects;
- Type Registry;
- SQLite persistence;
- ProjectStore;
- Leaflet-based 2D editing;
- existing V1 route preservation;
- scenario architecture;
- simulation architecture;
- TerrainContext;
- EngineAdapters;
- normalized SimulationResults;
- context layers;
- future scenario comparison.
5. Non-Goals
The following are explicitly outside the initial V2 architecture:
- replacing Flask;
- replacing Vanilla JS;
- introducing React/Vue/Svelte;
- replacing Leaflet;
- replacing existing engines;
- introducing PostGIS;
- introducing Redis;
- introducing Celery;
- introducing distributed workers;
- multi-user collaboration;
- complex authentication/authorization;
- economic calculations inside physical engines;
- full simulation history;
- undo/redo;
- project export/backup;
- full reporting system;
- complete 3D redesign;
- loading the entire MDT into memory.
These may be future features.
They MUST NOT influence Phase 1 architecture unless a factual implementation requirement proves otherwise.
6. System Overview
                         ATLAS V2
                            │
             ┌──────────────┴──────────────┐
             │                             │
        FRONTEND                        BACKEND
             │                             │
      ProjectStore                       Flask
             │                             │
      ┌──────┼──────┐               ┌──────┼──────┐
      │      │      │               │      │      │
   Leaflet Three.js UI            SQLite  Engines MDT
                                  │
                                  │
                           EngineAdapters
                                  │
                           TerrainContext
The core domain hierarchy is:
Project
 ├── BaseParcel
 ├── ProjectObjects
 ├── ContextLayers
 └── Scenarios
      └── ScenarioObjects
           └── SimulationResults
7. Domain Model
7.1 Project
A Project is the persistent workspace.
Project
  id
  name
  created_at
  updated_at
A Project has exactly one BaseParcel in V2.
8. BaseParcel
8.1 Purpose
BaseParcel represents the immutable geographic reference for a Project.
It contains:
geometry
bounding_box
crs
terrain_source_ref
8.2 Cardinality
V2 defines:
Project 1 ─── 1 BaseParcel
A Project has exactly one BaseParcel.
A future requirement for multiple parcels would be an architectural extension and is not part of V2.
8.3 Persistence
BaseParcel has its own persistence representation.
Suggested schema:
base_parcels
────────────────────────
id                  PK
project_id          FK UNIQUE
geometry_geojson
bounding_box_json
crs
terrain_source_ref
created_at
project_id MUST be unique.
8.4 Immutability
After creation, BaseParcel geometry MUST NOT be modified by normal ProjectObject or Scenario operations.
Changing the BaseParcel is considered a project-level operation and is outside the normal Phase 1 editing workflow.
9. ProjectObject
9.1 Structure
A ProjectObject is the generic editable object of the Project.
ProjectObject
  id
  project_id
  type
  name
  geometry
  parameters
  created_at
  updated_at
Persistence:
project_objects
────────────────────────
id                  PK
project_id          FK
type
name
geometry_geojson
parameters_json
created_at
updated_at
9.2 No Object Subclasses
The following architecture is explicitly forbidden:
PondObject extends ProjectObject
PlatformObject extends ProjectObject
AccessObject extends ProjectObject
All objects use the same persistence and domain structure.
9.3 Object Semantics
Semantic information is derived from:
type
→ Type Registry
The ProjectObject MUST NOT contain a duplicate category field.
10. Type Registry
10.1 Purpose
The Type Registry is the central configuration source for object semantics.
It is configuration, not an object-class hierarchy.
Example:
types:

  zone:
    allowed_geometry_types:
      - Polygon
    parameter_schema: {}
    render_style: zone_outline

  pond:
    allowed_geometry_types:
      - Polygon
    parameter_schema:
      target_depth:
        type: number
        required: false
    render_style: water_body

  platform:
    allowed_geometry_types:
      - Polygon
    parameter_schema:
      target_elevation:
        type: number
        required: true
    render_style: platform

  access:
    allowed_geometry_types:
      - LineString
      - Polygon
    parameter_schema: {}
    render_style: path

  crop_area:
    allowed_geometry_types:
      - Polygon
    parameter_schema: {}
    render_style: crop_zone
10.2 Phase 1 Registry Contract
Phase 1 consumes:
type
allowed_geometry_types
parameter_schema
render_style
10.3 Phase 2 Registry Contract
The registry structure MUST also support:
engines
category
modifiable_terrain
allow_outside_parcel
These fields do not need active consumers in Phase 1.
They MAY contain defaults or empty values until Phase 2.
10.4 Parameter Schema
The Type Registry defines the schema of parameters.
This is mandatory.
Free-form JSON without validation is NOT accepted as the final contract.
The schema defines:
- field names;
- types;
- required fields;
- optional fields;
- future UI metadata as necessary.
Example:
parameter_schema:
  target_elevation:
    type: number
    required: true

  target_slope:
    type: number
    required: false
10.5 Validation Responsibilities
Parameter validation occurs in two places:
ProjectStore
Validates before persistence.
EngineAdapter
Validates again before passing parameters to the V1 engine.
This is intentional defense in depth.
11. Geometry Model
11.1 Representation
Geometries are communicated and persisted as GeoJSON.
GeoJSON is used because it is:
- standard;
- readable;
- compatible with Leaflet;
- suitable for API communication;
- easy to serialize.
11.2 CRS
The internal working coordinate system remains:
TM06 / EPSG:3763
The existing transformation implementation MUST be preserved.
No silent replacement of the CRS is allowed.
12. Geometry Validation
Geometry validation occurs before persistence and again before engine execution.
12.1 Invalid Geometry
The following MUST be rejected:
self-intersecting polygon
zero-area geometry
negative-area geometry
invalid topology
geometry incompatible with object type
completely outside BaseParcel
12.2 Partially Outside BaseParcel
A geometry that is partially outside the BaseParcel is:
WARNING
and MAY be persisted.
It MUST NOT automatically be rejected.
Reason:
- access roads may connect to external roads;
- drainage may leave the parcel;
- fences may follow boundaries;
- utility connections may cross the boundary.
12.3 Completely Outside BaseParcel
A geometry entirely outside the BaseParcel is rejected by default.
The Type Registry may later define:
allow_outside_parcel: true
for types where this is legitimate.
12.4 Validation Matrix
Condition                              Action

Invalid topology                       REJECT
Zero area                              REJECT
Wrong geometry type                    REJECT
Completely outside BaseParcel          REJECT
Partially outside BaseParcel           WARNING + ALLOW
Inside BaseParcel                      ACCEPT
12.5 Frontend Validation
The ProjectStore validates:
- topology;
- geometry type;
- area;
- containment;
- Type Registry compatibility.
Validation occurs during drawing/editing and before persistence.
12.6 Backend Validation
EngineAdapters repeat:
- topology validation;
- geometry type validation;
- parameter validation.
The adapter does not need to reject partially outside geometries because engines may legitimately require geometry extending beyond the parcel.
13. Scenario Model
13.1 Purpose
Scenarios represent isolated What-If states.
A Scenario contains copies of ProjectObjects.
ProjectObject
     │
     │ copy
     ▼
ScenarioObject
13.2 Scenario Persistence
scenarios
────────────────────
id                  PK
project_id          FK
name
created_at
updated_at
14. ScenarioObject
14.1 Identity
A ScenarioObject has its own identity.
project_object.id
        ≠
scenario_object.id
The ScenarioObject is an independent persisted object.
14.2 Structure
ScenarioObject
  id
  scenario_id
  original_object_id
  type
  name
  geometry
  parameters
  snapshot_version
  snapshot_updated_at
  created_at
Persistence:
scenario_objects
────────────────────────────
id                      PK
scenario_id             FK
original_object_id      FK nullable
type
name
geometry_geojson
parameters_json
snapshot_version
snapshot_updated_at
created_at
14.3 original_object_id
original_object_id exists for provenance.
It answers:
"Which ProjectObject did this ScenarioObject originate from?"

It does NOT imply synchronization.
It does NOT make the ScenarioObject dependent on the ProjectObject.
It is nullable because an object may be created directly inside a Scenario.
14.4 Deleting the Original ProjectObject
Deleting a ProjectObject MUST NOT delete its ScenarioObjects.
The foreign key behavior is:
original_object_id
    ON DELETE SET NULL
Therefore:
ProjectObject deleted
        ↓
ScenarioObject survives
        ↓
original_object_id becomes NULL
The ScenarioObject remains fully usable.
15. Snapshot Lifecycle
15.1 Initial Snapshot
When a Scenario is created from a Project:
ProjectObject
      ↓
copy
      ↓
ScenarioObject
The copy receives:
snapshot_version = 1
snapshot_updated_at = now
15.2 No Automatic Synchronization
After creation:
ProjectObject changes
        ≠
ScenarioObject changes
There is no automatic synchronization.
This is mandatory.
15.3 Explicit Update From Project
The user may explicitly request:
Update Scenario From Project
The existing ScenarioObject identity is retained.
The contents are replaced:
same scenario_object_id
new geometry
new parameters
new name
new type
snapshot_version += 1
snapshot_updated_at = now
This is an UPDATE.
It is NOT:
DELETE + INSERT
15.4 Why Identity Is Preserved
Preserving identity avoids:
- broken UI references;
- orphaned results;
- unnecessary delete/recreate logic;
- unnecessary identity churn.
The semantic meaning is:
"This is still the same object in this scenario; its snapshot has been refreshed."

16. Scenario Duplication
When a Scenario is duplicated:
Scenario
   ↓
new Scenario
   ↓
copy ScenarioObjects
The copied ScenarioObjects receive new IDs.
Their:
original_object_id
continues to identify their ProjectObject provenance.
16.1 Simulation Results Are NOT Copied
SimulationResults are derived data.
When a Scenario is duplicated:
ScenarioObjects → copied
SimulationResults → NOT copied
The new Scenario starts without simulation results.
Results must be recalculated.
17. Baseline
V2 does not persist a formal "Scenario 0".
The baseline is virtual.
It represents:
BaseParcel
+
ProjectObjects
without requiring a persisted Scenario containing copies of the ProjectObjects.
Analysis that does not represent an intervention may operate directly at Project level.
A first real What-If Scenario is a persisted Scenario.
This avoids a phantom Scenario containing redundant copies.
18. Parameters
18.1 ScenarioObject.parameters
The ScenarioObject contains the default parameter set used when no explicit simulation parameters are supplied.
18.2 simulation_parameters
The simulation API accepts an optional:
simulation_parameters
This is an ephemeral parameter set for one execution.
It MUST NOT modify the ScenarioObject.
18.3 No Merge Semantics
The contract is:
simulation_parameters absent
    ↓
effective_parameters =
ScenarioObject.parameters
or:
simulation_parameters present
    ↓
effective_parameters =
simulation_parameters
There is NO merge.
There is NO partial override.
There is NO:
ScenarioObject.parameters + simulation_parameters
operation.
18.4 Full Replacement
If simulation_parameters is supplied, it represents the COMPLETE parameter set for that execution.
The frontend is responsible for constructing the complete parameter object.
Example:
{
  "scenario_id": "scenario-123",
  "scenario_object_id": "scenario-object-456",
  "engine_type": "earthwork",
  "simulation_parameters": {
    "target_elevation": 44.5,
    "target_slope": 2.0
  }
}
18.5 Validation
simulation_parameters are validated against the same Type Registry parameter schema as ScenarioObject parameters.
Validation occurs:
ProjectStore
    ↓
API
    ↓
EngineAdapter
19. Simulation Model
19.1 Simulation Is an Execution Concept
Simulation is not a persisted database entity.
It represents the act of:
receiving input
→ executing an engine
→ producing a result
19.2 No simulations Table
There is no:
simulations
table.
The only persisted simulation artefact is:
simulation_results
20. SimulationResult
20.1 Purpose
SimulationResult is the normalized persisted output of an engine execution.
Structure:
SimulationResult
  id
  scenario_id
  scenario_object_id
  engine_type
  parameters_used
  status
  metrics
  derived_geometries
  warnings
  errors
  limitations
  computation_time_ms
  computed_at
20.2 Persistence
simulation_results
────────────────────────────
id                      PK
scenario_id             FK
scenario_object_id      FK
engine_type
parameters_used_json
status
metrics_json
derived_geometries_json
warnings_json
errors_json
limitations_json
computation_time_ms
computed_at
20.3 Result Ownership
A SimulationResult belongs to:
Scenario
    ↓
ScenarioObject
It MUST reference:
scenario_object_id
It MUST NOT reference:
project_object_id
This is essential for scenario isolation.
21. SimulationResult Parameters
Every successful or partial SimulationResult stores:
parameters_used
This is the complete effective parameter set used by the engine.
This allows:
- auditing;
- reproduction;
- comparison;
- debugging;
- future reporting.
Example:
{
  "target_elevation": 44.5,
  "target_slope": 2.0
}
22. Simulation Status
A SimulationResult may have:
success
partial
error
These indicate the execution result.
They do NOT indicate whether the result is stale.
Staleness is derived separately.
23. Latest Result Semantics
V2 does not maintain execution history.
For each:
scenario_object_id
+
engine_type
there is at most one persisted SimulationResult.
When a new simulation is run:
existing result
       ↓
replace
       ↓
new result
Implementation may use:
UPDATE
or:
DELETE + INSERT
depending on implementation convenience.
The semantic contract is:
Only the latest result is persisted.

24. Staleness
24.1 Principle
A SimulationResult is factual.
It represents:
"These parameters and this object state produced this result."

The result itself does not mutate when the ScenarioObject changes.
24.2 No Stored Stale Flag
The following are explicitly forbidden:
SimulationResult.stale
ScenarioObject.simulation_state
Staleness is derived.
24.3 V2 Staleness Rule
A result is stale when:
ScenarioObject.snapshot_updated_at
>
SimulationResult.computed_at
The timestamp comparison is the V2 staleness contract.
24.4 Why Timestamp Comparison Is Sufficient
Every mutation of a ScenarioObject MUST update:
snapshot_updated_at
Therefore any mutation occurring after computation produces:
snapshot_updated_at > computed_at
No independent parameter comparison is required in V2.
24.5 API Representation
The backend MAY return:
{
  "is_stale": true
}
This is a derived field.
It is NOT persisted.
24.6 UI Behavior
A stale result remains visible.
The UI should indicate:
Result outdated
Recalculate
The old result is not immediately destroyed.
When the new result arrives, it replaces the old result.
25. Simulation API
25.1 Run Simulation
POST /api/v2/simulations/run
Request:
{
  "scenario_id": "scenario-123",
  "scenario_object_id": "scenario-object-456",
  "engine_type": "earthwork",
  "simulation_parameters": {
    "target_elevation": 44.5
  }
}
simulation_parameters is optional.
25.2 Execution Contract
If absent:
ScenarioObject.parameters
are used.
If present:
simulation_parameters
are used in full.
No merge occurs.
25.3 Result Contract
The response contains:
{
  "id": "result-789",
  "scenario_id": "scenario-123",
  "scenario_object_id": "scenario-object-456",
  "engine_type": "earthwork",
  "parameters_used": {
    "target_elevation": 44.5
  },
  "status": "success",
  "metrics": {},
  "derived_geometries": [],
  "warnings": [],
  "errors": [],
  "limitations": [],
  "computation_time_ms": 124,
  "computed_at": "2026-08-19T15:00:00Z",
  "is_stale": false
}
is_stale is derived.
26. EngineAdapter
26.1 Purpose
EngineAdapters isolate V2 from existing V1 engines.
Architecture:
V2 Domain
    ↓
EngineAdapter
    ↓
V1 Engine
26.2 Adapter Responsibilities
An adapter is responsible for:
validate_input()
to_motor_input()
execute motor
from_motor_output()
It converts between:
V2 domain contract
and:
V1 engine contract
26.3 Existing Engines
V1 engines SHOULD remain unchanged.
If an engine is tightly coupled to Flask, filesystem state, global variables, or other infrastructure, Phase 0 must identify it.
The Migration Map classifies required intervention as:
KEEP
ADAPT
REFACTOR
27. TerrainContext
27.1 Purpose
TerrainContext provides controlled access to terrain data.
It is a service.
It is NOT a persisted domain entity.
27.2 Lifecycle
TerrainContext is:
lazy-created
project-session scoped
It is not created simply because a Project is opened.
It is created when a simulation or engine first requires terrain data.
27.3 Scope
One TerrainContext exists per active Project session.
Multiple simulations may reuse the same TerrainContext.
This allows terrain data caching between:
earthwork simulation
pond simulation
solar simulation
27.4 Internal Structure
TerrainContext
 ├── project_id
 ├── bounding_box
 ├── crs
 ├── transformation
 ├── dataset_reference
 └── internal cache
27.5 Methods
Expected interface:
elevation(point)
elevations(polygon)
profile(line)
clip(bounds)
slope(area)
fill_cache(bounds)
The exact method set may evolve when the first V1 engine is adapted.
27.6 Lazy Raster Loading
TerrainContext does not load the complete MDT.
When an engine requests terrain:
request
 ↓
check cache
 ↓
cache hit → return
cache miss → load clip → cache → return
27.7 Cache
Initial implementation may use an in-memory cache.
An LRU strategy is preferred if memory pressure requires bounded cache size.
The exact cache size remains implementation-dependent.
27.8 Persistence
TerrainContext is NOT stored in SQLite.
Only its source metadata is persisted in BaseParcel:
terrain_source_ref
bounding_box
crs
28. Frontend Architecture
28.1 ProjectStore
ProjectStore is the central frontend state manager.
It owns:
currentProject
baseParcel
objects[]
scenarios[]
activeScenarioId
simulationResults{}
uiState
lastError
28.2 Single Backend Boundary
All backend communication goes through ProjectStore.
Forbidden:
component → fetch()
tool → fetch()
leaflet handler → fetch()
Required:
UI
 ↓
ProjectStore
 ↓
API
28.3 Pub/Sub
ProjectStore exposes state changes through pub/sub.
Consumers:
Leaflet
Three.js
UI panels
forms
toolbars
subscribe to Store state.
28.4 Leaflet
Leaflet remains the primary 2D map interface.
It consumes ProjectStore state.
Leaflet should not become the owner of domain state.
28.5 Three.js
Three.js may consume ProjectStore state.
3D is not part of the Phase 1 foundation rewrite.
29. Frontend Error Handling
ProjectStore must expose errors to the UI.
At minimum:
lastError
or an equivalent event mechanism.
Errors include:
- network failure;
- validation failure;
- persistence failure;
- simulation failure;
- unexpected backend errors.
29.1 UI Error Handling
The UI must have a generic error presentation mechanism.
Examples:
toast
inline validation message
error panel
The exact presentation is a UI decision.
29.2 State Safety
A failed simulation MUST NOT corrupt:
Project
Scenario
ScenarioObject
A simulation error produces a result/error response, not a mutation of domain state.
30. Backend Architecture
30.1 Flask
Flask remains the backend framework.
There is no architectural reason to replace it.
30.2 API
V2 API routes use:
/api/v2/...
V1 routes remain available.
30.3 API Simplicity
V2 does not introduce:
- complex version negotiation;
- public API authentication;
- pagination infrastructure;
- external API contracts;
- asynchronous job queues.
These are not required by the current product.
31. Persistence
31.1 SQLite
SQLite is the V2 Phase 1 persistence layer.
It is the source of truth for Project state.
31.2 Tables
Initial architecture:
projects
base_parcels
project_objects
scenarios
scenario_objects
simulation_results
Context layer configuration may be stored separately or represented by configuration files.
32. Project Persistence
projects
────────────────────
id              PK
name
created_at
updated_at
33. BaseParcel Persistence
base_parcels
────────────────────────
id                  PK
project_id          FK UNIQUE
geometry_geojson
bounding_box_json
crs
terrain_source_ref
created_at
34. ProjectObject Persistence
project_objects
────────────────────────
id                  PK
project_id          FK
type
name
geometry_geojson
parameters_json
created_at
updated_at
35. Scenario Persistence
scenarios
────────────────────
id                  PK
project_id          FK
name
created_at
updated_at
36. ScenarioObject Persistence
scenario_objects
────────────────────────────
id                      PK
scenario_id             FK
original_object_id      FK nullable
type
name
geometry_geojson
parameters_json
snapshot_version
snapshot_updated_at
created_at
Foreign key:
original_object_id
ON DELETE SET NULL
37. SimulationResult Persistence
simulation_results
────────────────────────────
id                      PK
scenario_id             FK
scenario_object_id      FK
engine_type
parameters_used_json
status
metrics_json
derived_geometries_json
warnings_json
errors_json
limitations_json
computation_time_ms
computed_at
There is no simulations table.
38. Persistence Ownership Rules
Project
 ├── owns BaseParcel
 ├── owns ProjectObjects
 ├── owns Scenarios
 │    └── owns ScenarioObjects
 │          └── owns SimulationResults
A ScenarioObject is independent from its source ProjectObject.
A SimulationResult is dependent on the ScenarioObject.
39. Context Layers
ContextLayers represent informational geographic layers.
Examples:
PDM
RAN
REN
Cadastro
Solos
They are not intervention objects.
39.1 Configuration
Available ContextLayers are globally configured.
They are not defined independently inside every Project.
39.2 Project State
A Project stores only user-specific layer state:
layer_id
visible
opacity
where applicable.
39.3 Context Layer Restrictions
ContextLayers:
- are not simulations;
- do not participate in scenarios;
- do not become ScenarioObjects;
- do not modify terrain;
- do not require ProjectObject persistence.
40. API Surface
40.1 Projects
GET    /api/v2/projects
POST   /api/v2/projects
GET    /api/v2/projects/{id}
PUT    /api/v2/projects/{id}
DELETE /api/v2/projects/{id}
40.2 ProjectObjects
GET    /api/v2/projects/{id}/objects
POST   /api/v2/projects/{id}/objects
PUT    /api/v2/projects/{id}/objects/{object_id}
DELETE /api/v2/projects/{id}/objects/{object_id}
40.3 Scenarios
GET    /api/v2/projects/{id}/scenarios
POST   /api/v2/projects/{id}/scenarios
GET    /api/v2/projects/{id}/scenarios/{scenario_id}
PUT    /api/v2/projects/{id}/scenarios/{scenario_id}
DELETE /api/v2/projects/{id}/scenarios/{scenario_id}
40.4 ScenarioObject Refresh
Explicit operation:
POST
/api/v2/projects/{project_id}/scenarios/{scenario_id}/objects/{scenario_object_id}/update-from-project
This operation:
1. locates original_object_id;
2. reads the current ProjectObject;
3. updates the existing ScenarioObject;
4. increments snapshot_version;
5. updates snapshot_updated_at.
SimulationResults remain stored but become stale through timestamp derivation.
40.5 Simulation
POST /api/v2/simulations/run
Request:
{
  "scenario_id": "...",
  "scenario_object_id": "...",
  "engine_type": "...",
  "simulation_parameters": {}
}
41. Simulation Validation
Before execution:
scenario exists
scenario_object exists
scenario_object belongs to scenario
engine_type is supported
geometry is valid
geometry type is allowed
parameters satisfy Type Registry schema
Failure prevents engine execution.
42. Simulation Execution Flow
ProjectStore
    │
    ▼
POST /api/v2/simulations/run
    │
    ▼
Backend validates request
    │
    ▼
Load ScenarioObject
    │
    ▼
Resolve effective parameters
    │
    ├── simulation_parameters supplied
    │        ↓
    │   use complete supplied set
    │
    └── absent
             ↓
       use ScenarioObject.parameters
    │
    ▼
Type Registry validation
    │
    ▼
EngineAdapter.validate_input()
    │
    ▼
TerrainContext if required
    │
    ▼
V1 Engine
    │
    ▼
EngineAdapter.from_motor_output()
    │
    ▼
SimulationResult
    │
    ▼
Persist latest result
    │
    ▼
Return result
43. Data Lifecycle
43.1 Project Creation
Create Project
    ↓
Create BaseParcel
    ↓
Persist
43.2 Object Creation
Draw geometry
    ↓
Validate geometry
    ↓
Validate type
    ↓
Validate parameters
    ↓
ProjectStore
    ↓
SQLite
43.3 Object Editing
Edit
 ↓
Validate
 ↓
Persist
43.4 Scenario Creation
ProjectObjects
      ↓
copy
      ↓
ScenarioObjects
43.5 Scenario Editing
ScenarioObjects are edited independently.
The original ProjectObjects remain unchanged.
43.6 Scenario Simulation
ScenarioObject
      +
effective parameters
      ↓
EngineAdapter
      ↓
SimulationResult
43.7 Scenario Update From Project
ProjectObject
      ↓
explicit refresh
      ↓
existing ScenarioObject
      ↓
UPDATE
      ↓
snapshot_version += 1
      ↓
snapshot_updated_at = now
Existing SimulationResults become stale by timestamp comparison.
44. Deletion Rules
44.1 ProjectObject
Deleting a ProjectObject:
does not delete ScenarioObjects
Its original_object_id references become NULL through:
ON DELETE SET NULL
44.2 ScenarioObject
Deleting a ScenarioObject removes its associated SimulationResult.
SimulationResults have no independent value without the ScenarioObject.
44.3 Scenario
Deleting a Scenario removes:
ScenarioObjects
SimulationResults
belonging to that Scenario.
45. Concurrency
SQLite assumes:
single-user / low-concurrency
The initial V2 architecture does not target:
- multi-user simultaneous editing;
- distributed backend;
- collaborative editing.
Multiple browser tabs may create conflicting writes.
This is a known limitation.
If multi-user or serious concurrent editing becomes a requirement, migration to PostgreSQL is the likely future direction.
This is not part of V2 Phase 1.
46. Units and Precision
Physical engines should produce values in SI units where applicable.
Examples:
metres
square metres
cubic metres
hectares
percentages
The engine should preserve native computational precision.
Formatting, rounding and presentation precision are responsibilities of:
UI
reporting
presentation layer
They are not engine responsibilities.
47. CRS and Coordinate Transformation
TM06 / EPSG:3763 is a critical compatibility requirement.
The V2 architecture assumes that existing V1 calculations depend on the current transformation.
Therefore:
DO NOT replace
DO NOT simplify
DO NOT silently reproject
DO NOT introduce an alternative transformation
without explicit evidence from the Phase 0 audit.
The audit must identify:
- transformation functions;
- coordinate conversions;
- frontend coordinate handling;
- engine coordinate handling;
- MDT coordinate assumptions.
The long-term objective is to centralize terrain-related access through TerrainContext without changing the underlying mathematics.
48. Migration Strategy
V2 is an incremental migration.
The migration strategy is:
existing V1 engine
        ↓
audit
        ↓
adapter
        ↓
V2 domain contract
49. Phase 0 — V1 Audit
Phase 0 is mandatory.
The audit produces:
ATLAS_V1_AUDIT.md
The audit must inventory:
Backend
- Flask routes;
- engine modules;
- utility modules;
- file access;
- configuration;
- environment variables;
- global state.
Engines
For each engine:
inputs
outputs
dependencies
filesystem access
Flask coupling
global state
coordinate assumptions
MDT access
error behavior
Frontend
Classify JavaScript functions as:
UI
DOMAIN
UTILITY
Identify:
- global variables;
- duplicated state;
- direct fetch calls;
- Leaflet state;
- Three.js state;
- business logic mixed into rendering;
- validation logic.
Terrain
Map:
- MDT loading;
- raster access;
- clipping;
- coordinate transformations;
- slope calculations;
- elevation access.
50. Migration Risks
50.1 Flask Coupling
V1 engines may directly access:
request
flask.current_app
session
or other Flask-specific state.
Phase 0 must identify this.
50.2 Filesystem Coupling
Engines may depend on:
- hardcoded paths;
- temporary files;
- fixed output directories;
- environment-specific locations.
These must be documented.
50.3 Coordinate Transformation Duplication
TM06 transformations may exist in multiple places.
The audit must identify every use.
50.4 Frontend Domain Logic
Existing frontend code may mix:
rendering
state
validation
business logic
API communication
The migration must identify this before ProjectStore implementation.
51. Phase Plan
Phase 0 — V1 Audit
Deliverable:
ATLAS_V1_AUDIT.md
Scope:
- repository inventory;
- engine mapping;
- Flask coupling;
- frontend state mapping;
- CRS mapping;
- MDT mapping;
- migration classification.
No V2 feature implementation.
52. Phase 1 — Workspace Foundation
Phase 1 contains:
Project
BaseParcel
ProjectObject
Type Registry
ProjectStore
SQLite
CRUD
Leaflet editing
validation
save
load
reopen
delete
The Phase 1 success condition is:
Create project
→ draw objects
→ edit objects
→ save
→ close
→ reopen
→ state is intact
52.1 Explicitly NOT in Phase 1
TerrainContext
Engines
EngineAdapters
Simulation
SimulationResults
Scenarios
What-If
3D redesign
TerrainContext is not built until a consumer exists.
53. Phase 2 — First Engine
Phase 2 introduces:
TerrainContext
EngineAdapter
earthwork engine integration
SimulationResult
simulation API
The first complete flow becomes:
draw
 ↓
configure
 ↓
simulate
 ↓
engine
 ↓
result
 ↓
visualize
Earthwork is the first target because it is the simplest existing structured engine.
54. Phase 3 — Scenarios
Phase 3 introduces:
Scenarios
ScenarioObjects
snapshot isolation
scenario duplication
Update Scenario From Project
staleness
comparison
What-If
55. Phase 4 — Engine Expansion
Future adapters:
pond
solar
agriculture
drainage
other V1 engines
Context layers and reporting can expand here as consumers appear.
56. Deferred Features
The following are deliberately deferred:
Undo / Redo
Smart-CAD-style undo/redo is expected eventually but is not part of Phase 1 architecture.
It must not be implemented ad hoc before the state model is stable.
Export / Backup
Future functionality may include:
GeoJSON export
project backup
reports
Not part of Phase 1.
Simulation History
Only the latest result is persisted.
Historical runs are deferred.
Multi-user Collaboration
Not part of V2 initial architecture.
PostgreSQL
Not required until concurrency or multi-user requirements justify it.
Distributed Simulation
No Celery/Redis/job infrastructure until asynchronous execution becomes a real requirement.
57. Economic Calculations
Physical engines remain physically focused.
They produce:
geometry
volume
slope
elevation
area
other physical metrics
They do not calculate:
construction cost
ROI
economic feasibility
financial return
Economic analysis is a future layer.
58. Architectural Anti-Patterns
The following are explicitly forbidden unless a new architectural decision is formally approved.
58.1 Object Class Hierarchy
Do not create:
PondObject
PlatformObject
AccessObject
58.2 Duplicate Type Semantics
Do not store:
ProjectObject.category
if category is already defined by the Type Registry.
58.3 Direct Backend Fetches
Do not allow UI components to bypass ProjectStore.
58.4 Browser-Only Persistence
Do not treat localStorage as the authoritative Project store.
58.5 Scenario References to ProjectObjects
SimulationResults and Scenario logic MUST reference ScenarioObjects.
58.6 Simulation Parameter Merge
Do not implement:
object parameters + simulation parameters
Simulation parameters are complete replacement inputs.
58.7 Automatic Snapshot Synchronization
Editing a ProjectObject must not silently modify ScenarioObjects.
58.8 Simulation History
Do not accumulate simulation execution history in Phase 2.
58.9 Premature Infrastructure
Do not introduce:
PostGIS
Redis
Celery
microservices
React
without an actual consumer.
59. Decision Register
The following decisions are frozen.
ID	Decision	Status
DEC-001	Project is persistent workspace	FROZEN
DEC-002	SQLite from Phase 1	FROZEN
DEC-003	Project has exactly one BaseParcel in V2	FROZEN
DEC-004	BaseParcel is immutable	FROZEN
DEC-005	ProjectObject is a flat generic model	FROZEN
DEC-006	Type Registry provides object semantics	FROZEN
DEC-007	No category field on ProjectObject	FROZEN
DEC-008	Type Registry is configuration, not code	FROZEN
DEC-009	Phase 1 Registry includes geometry/schema/rendering	FROZEN
DEC-010	Phase 2 Registry adds engine semantics	FROZEN
DEC-011	GeoJSON is the geometry communication format	FROZEN
DEC-012	TM06/EPSG:3763 remains unchanged	FROZEN
DEC-013	Geometry validation occurs before persistence	FROZEN
DEC-014	Geometry validation repeats in EngineAdapter	FROZEN
DEC-015	Partially outside BaseParcel = warning	FROZEN
DEC-016	Completely outside BaseParcel = reject	FROZEN
DEC-017	ScenarioObjects have independent identity	FROZEN
DEC-018	original_object_id exists for provenance	FROZEN
DEC-019	original_object_id uses ON DELETE SET NULL	FROZEN
DEC-020	No automatic ProjectObject → ScenarioObject synchronization	FROZEN
DEC-021	Explicit Update Scenario From Project operation	FROZEN
DEC-022	Snapshot update preserves scenario_object_id	FROZEN
DEC-023	Snapshot update increments snapshot_version	FROZEN
DEC-024	snapshot_updated_at tracks snapshot mutation	FROZEN
DEC-025	Scenario duplication copies objects, not results	FROZEN
DEC-026	Baseline is virtual, not persisted as Scenario 0	FROZEN
DEC-027	Simulation is an execution concept, not DB entity	FROZEN
DEC-028	No simulations table	FROZEN
DEC-029	SimulationResult is the persisted simulation artefact	FROZEN
DEC-030	SimulationResult references scenario_object_id	FROZEN
DEC-031	SimulationResult never references ProjectObject directly	FROZEN
DEC-032	simulation_parameters is optional	FROZEN
DEC-033	simulation_parameters uses complete replacement	FROZEN
DEC-034	No parameter merge semantics	FROZEN
DEC-035	Simulation does not mutate ScenarioObject	FROZEN
DEC-036	SimulationResult stores parameters_used	FROZEN
DEC-037	Only latest result per object/engine is persisted	FROZEN
DEC-038	SimulationResult is factual/immutable	FROZEN
DEC-039	Staleness is derived, not persisted	FROZEN
DEC-040	snapshot_updated_at > computed_at means stale	FROZEN
DEC-041	TerrainContext is lazy	FROZEN
DEC-042	TerrainContext is Project-session scoped	FROZEN
DEC-043	TerrainContext is not persisted	FROZEN
DEC-044	Existing V1 engines are preserved	FROZEN
DEC-045	EngineAdapters isolate V2 from V1	FROZEN
DEC-046	Flask remains backend framework	FROZEN
DEC-047	Vanilla JS remains frontend architecture	FROZEN
DEC-048	ProjectStore is sole backend communication boundary	FROZEN
DEC-049	No React/Vue/Svelte migration	FROZEN
DEC-050	No PostGIS/Celery/Redis in initial V2	FROZEN
DEC-051	ContextLayers are globally configured	FROZEN
DEC-052	ContextLayer visibility is project-specific	FROZEN
DEC-053	ContextLayers do not participate in scenarios	FROZEN
DEC-054	Phase 1 contains no engines	FROZEN
DEC-055	Phase 1 contains no TerrainContext	FROZEN
DEC-056	Phase 0 audits factual V1 compatibility	FROZEN
DEC-057	Architecture is not reopened during Phase 1	FROZEN
DEC-058	Undo/Redo is deferred	FROZEN
DEC-059	Export/Backup is deferred	FROZEN
DEC-060	Multi-user collaboration is deferred	FROZEN


60. Known Limitations
The initial architecture intentionally accepts:
SQLite concurrency limitations
single-user assumptions
synchronous simulation execution
no historical simulation runs
no collaborative editing
no distributed workers
These are conscious constraints, not architectural oversights.
61. Architectural Risks
Risk 1 — V1 Engine Coupling
A V1 engine may not actually be isolated from Flask or filesystem state.
Mitigation:
Phase 0 audit
→ classify
→ adapt/refactor only where necessary
Risk 2 — CRS Logic Is Scattered
The TM06 transformation may exist in multiple modules.
Mitigation:
Phase 0 mapping
→ identify all usage
→ preserve mathematics
→ progressively centralize terrain access
Risk 3 — Frontend Domain Logic Is Scattered
The existing frontend may contain business logic inside rendering code.
Mitigation:
Phase 0 classification
→ UI / DOMAIN / UTILITY
→ move domain state into ProjectStore
Risk 4 — Geometry Validation Complexity
Different V1 engines may have different geometry expectations.
Mitigation:
Type Registry
+
ProjectStore validation
+
EngineAdapter validation
Risk 5 — Future Multi-user Requirements
SQLite is not the final architecture for collaborative multi-user operation.
Mitigation:
Do not prematurely introduce PostgreSQL.
Migrate only when the product requires concurrency.
62. Final Architecture
╔══════════════════════════════════════════════════════════╗
║                    ATLAS V2                              ║
║         Laboratório de Viabilidade Física de Terrenos    ║
╚══════════════════════════════════════════════════════════╝


PROJECT
│
├── BASE PARCEL
│     ├── geometry
│     ├── bounding_box
│     ├── CRS / EPSG:3763
│     └── terrain_source_ref
│
├── PROJECT OBJECTS
│     ├── id
│     ├── type
│     ├── name
│     ├── geometry
│     └── parameters
│
├── CONTEXT LAYERS
│     ├── global configuration
│     └── project visibility state
│
└── SCENARIOS
      │
      └── SCENARIO OBJECTS
            ├── id
            ├── original_object_id
            ├── snapshot_version
            ├── snapshot_updated_at
            ├── geometry
            └── parameters
                  │
                  └── SIMULATION RESULTS
                        ├── engine_type
                        ├── parameters_used
                        ├── status
                        ├── metrics
                        ├── derived_geometries
                        ├── warnings
                        ├── errors
                        ├── limitations
                        └── computed_at


TYPE REGISTRY
│
├── allowed_geometry_types
├── parameter_schema
├── render_style
│
└── Phase 2:
      ├── engines
      ├── category
      ├── modifiable_terrain
      └── allow_outside_parcel


FRONTEND
│
├── ProjectStore
│     ├── currentProject
│     ├── baseParcel
│     ├── objects
│     ├── scenarios
│     ├── simulationResults
│     └── uiState
│
├── Leaflet
├── Three.js
└── UI


BACKEND
│
├── Flask
│
├── SQLite
│
├── EngineAdapters
│      │
│      └── V1 Engines
│
└── TerrainContext
       ├── lazy
       ├── project-session scoped
       ├── cache
       └── MDT


SIMULATION FLOW

ScenarioObject
      │
      ├── geometry
      ├── parameters
      │
      └── optional simulation_parameters
                    │
                    ▼
             effective parameters
                    │
                    ▼
             EngineAdapter
                    │
                    ▼
               V1 Engine
                    │
                    ▼
             SimulationResult
                    │
                    ▼
              SQLite / API


STALE DETECTION

ScenarioObject.snapshot_updated_at
                  │
                  │ >
                  ▼
SimulationResult.computed_at

        TRUE → is_stale
        FALSE → current
63. Implementation Sequence
The implementation sequence is intentionally strict.
PHASE 0
V1 AUDIT
    ↓
ATLAS_V1_AUDIT.md
    ↓
verify factual compatibility
    ↓
PHASE 1
WORKSPACE FOUNDATION
    ↓
ProjectStore
Project
BaseParcel
ProjectObjects
Type Registry
SQLite
CRUD
Geometry validation
    ↓
PHASE 2
FIRST ENGINE
    ↓
TerrainContext
EngineAdapter
Earthwork
SimulationResult
Simulation API
    ↓
PHASE 3
SCENARIOS
    ↓
Scenario
ScenarioObjects
Snapshot isolation
Update From Project
Staleness
Comparison
    ↓
PHASE 4
ENGINE EXPANSION
    ↓
Pond
Solar
Agriculture
Drainage
Context layers
Reports
64. Freeze Statement
The architecture is now considered frozen.
The following are no longer open design questions:
- Project persistence;
- SQLite;
- BaseParcel cardinality;
- ProjectObject model;
- Type Registry;
- parameter schema;
- geometry validation;
- ScenarioObject identity;
- snapshot lifecycle;
- scenario isolation;
- simulation parameter semantics;
- SimulationResult persistence;
- simulation result replacement;
- staleness;
- TerrainContext lifecycle;
- EngineAdapter strategy;
- Flask;
- Vanilla JS;
- ProjectStore;
- ContextLayer model;
- Phase boundaries.
No further conceptual architecture round is required.
65. Post-Freeze Rule
After freeze:
IMPLEMENT
    ↓
AUDIT
    ↓
TEST
    ↓
FIX
not:
IMPLEMENT
    ↓
REOPEN ARCHITECTURE
    ↓
REDESIGN
The only accepted reason to modify a frozen architectural decision is:
Phase 0 or implementation discovers a factual incompatibility with the existing V1 codebase that makes the frozen contract impossible or unsafe to implement.

Such a change must:
1. identify the factual incompatibility;
2. document the affected decision;
3. propose the smallest correction;
4. preserve all unaffected architectural decisions.
66. Immediate Next Action
The next deliverable is:
ATLAS_V1_AUDIT.md
The audit must begin from the actual V1 repository.
It must not assume that the architecture's assumptions about V1 are correct.
The purpose of Phase 0 is precisely to distinguish:
ARCHITECTURAL DECISION
from:
FACTUAL V1 REALITY
Once the audit is complete, Phase 1 may begin.
