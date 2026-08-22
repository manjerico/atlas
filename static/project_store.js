/* Atlas V2 Phase 1: the only frontend boundary for Atlas backend requests. */
(function () {
  class ProjectStore {
    constructor() {
      this.currentProject = null;
      this.baseParcel = null;
      this.objects = [];
      this.typeRegistry = {};
      this.scenarios = [];
      this.activeScenarioId = null;
      this.simulationResults = {};
      this.terrainView = { status: 'idle', data: null, error: null };
      this.planningProposal = { status: 'idle', preview: null, error: null };
      this.comparison = { status: 'idle', data: null, error: null };
      this.terrainSuitability = { status: 'idle', data: null, error: null };
      this.uiState = {
        sidebarCollapsed: false,
        activeWorkspaceView: 'explore',
        contextPanelOpen: false,
        objectComposerOpen: false,
        selectedObjectId: null,
        terrainViewOpen: false,
        terrainBaseMode: 'satellite',
        planningAssistantOpen: false,
        planningStep: 1,
        planningPlacementActive: false,
        planningDraft: {
          model: 'single_storey_house', width_m: 10, length_m: 14,
          floors: 1, height_m: 3.4, orientation_degrees: 0,
          earthwork_tolerance: 'balanced', platform_margin_m: 3,
          access_width_m: 3, include_platform: true, include_access: true,
          center: null,
        },
        suitabilityVisible: false,
      };
      this.lastError = null;
      this.listeners = new Set();
    }

    subscribe(listener) {
      this.listeners.add(listener);
      return () => this.listeners.delete(listener);
    }

    emit() {
      this.listeners.forEach((listener) => listener(this));
    }

    setUiState(patch) {
      this.uiState = { ...this.uiState, ...patch };
      this.emit();
    }

    setError(error) {
      this.lastError = error instanceof Error ? error.message : String(error);
      this.emit();
    }

    clearError() {
      this.lastError = null;
    }

    invalidateTerrainView() {
      this.terrainView = { status: 'idle', data: null, error: null };
    }

    resetPlanningProposal() {
      this.planningProposal = { status: 'idle', preview: null, error: null };
    }

    invalidateComparison() {
      this.comparison = { status: 'idle', data: null, error: null };
    }

    resetDecisionSupport() {
      this.invalidateComparison();
      this.terrainSuitability = { status: 'idle', data: null, error: null };
    }

    async request(path, options = {}) {
      const response = await fetch(`/api/v2${path}`, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      });
      if (response.status === 204) return null;
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || 'Erro inesperado no Atlas V2.');
      return body;
    }

    async requestBlob(path, options = {}) {
      const response = await fetch(`/api/v2${path}`, options);
      if (!response.ok) {
        let message = 'Não foi possível preparar o ficheiro.';
        try { message = (await response.json()).error || message; } catch (_) { /* resposta não JSON */ }
        throw new Error(message);
      }
      const disposition = response.headers.get('Content-Disposition') || '';
      const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const plain = disposition.match(/filename="?([^";]+)"?/i);
      return {
        blob: await response.blob(),
        filename: encoded ? decodeURIComponent(encoded[1]) : plain ? plain[1] : 'atlas-export',
      };
    }

    async downloadScenarioImage(view, options = {}) {
      if (!this.currentProject || !this.activeScenario) throw new Error('Abre primeiro uma alternativa.');
      try {
        const params = new URLSearchParams({ view });
        if (Array.isArray(options.bbox) && options.bbox.length === 4) params.set('bbox', options.bbox.join(','));
        return await this.requestBlob(`/projects/${this.currentProject.id}/scenarios/${this.activeScenario.id}/exports/image?${params.toString()}`);
      } catch (error) { this.setError(error); throw error; }
    }

    async downloadScenarioReport(level = 'simple') {
      if (!this.currentProject || !this.activeScenario) throw new Error('Abre primeiro uma alternativa.');
      try {
        return await this.requestBlob(`/projects/${this.currentProject.id}/scenarios/${this.activeScenario.id}/exports/report?level=${encodeURIComponent(level)}`);
      } catch (error) { this.setError(error); throw error; }
    }

    async createProject(name, baseParcel) {
      try {
        const project = await this.request('/projects', {
          method: 'POST', body: JSON.stringify({ name, base_parcel: baseParcel }),
        });
        this.currentProject = project;
        this.baseParcel = project.base_parcel;
        this.objects = [];
        this.scenarios = []; this.activeScenarioId = null; this.simulationResults = {};
        this.invalidateTerrainView();
        this.resetPlanningProposal();
        this.resetDecisionSupport();
        this.clearError(); this.emit();
        return project;
      } catch (error) { this.setError(error); throw error; }
    }

    async openProject(projectId) {
      try {
        const [project, objects, scenarios] = await Promise.all([
          this.request(`/projects/${projectId}`), this.request(`/projects/${projectId}/objects`),
          this.request(`/projects/${projectId}/scenarios`),
        ]);
        this.currentProject = project;
        this.baseParcel = project.base_parcel;
        this.objects = objects.objects;
        this.scenarios = scenarios.scenarios; this.activeScenarioId = null; this.simulationResults = {};
        this.invalidateTerrainView();
        this.resetPlanningProposal();
        this.resetDecisionSupport();
        this.clearError(); this.emit();
        return project;
      } catch (error) { this.setError(error); throw error; }
    }

    async listProjects() { return (await this.request('/projects')).projects; }

    async loadTypeRegistry() {
      try {
        this.typeRegistry = await this.request('/types');
        this.clearError(); this.emit();
        return this.typeRegistry;
      } catch (error) { this.setError(error); throw error; }
    }

    async listScenarios() {
      if (!this.currentProject) return [];
      return (await this.request(`/projects/${this.currentProject.id}/scenarios`)).scenarios;
    }

    async createScenario(name) {
      try {
        const scenario = await this.request(`/projects/${this.currentProject.id}/scenarios`, {
          method: 'POST', body: JSON.stringify({ name }),
        });
        this.scenarios = [...this.scenarios, scenario];
        this.activeScenarioId = scenario.id;
        this.invalidateTerrainView();
        this.resetPlanningProposal();
        this.invalidateComparison();
        this.clearError(); this.emit();
        return scenario;
      } catch (error) { this.setError(error); throw error; }
    }

    async openScenario(scenarioId) {
      try {
        const scenario = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenarioId}`);
        this.scenarios = [...this.scenarios.filter((item) => item.id !== scenario.id), scenario];
        this.activeScenarioId = scenario.id;
        this.simulationResults = (await this.request(`/projects/${this.currentProject.id}/scenarios/${scenarioId}/results`)).results.reduce((results, result) => {
          results[result.scenario_object_id] = { ...(results[result.scenario_object_id] || {}), [result.engine_type]: result };
          return results;
        }, {});
        this.invalidateTerrainView();
        this.resetPlanningProposal();
        this.invalidateComparison();
        this.clearError(); this.emit();
        return scenario;
      } catch (error) { this.setError(error); throw error; }
    }

    get activeScenario() { return this.scenarios.find((scenario) => scenario.id === this.activeScenarioId) || null; }

    async duplicateScenario(name) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      const duplicate = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/duplicate`, { method: 'POST', body: JSON.stringify({ name }) });
      this.scenarios = [...this.scenarios, duplicate]; this.activeScenarioId = duplicate.id; this.simulationResults = {}; this.invalidateTerrainView(); this.resetPlanningProposal(); this.invalidateComparison(); this.emit();
      return duplicate;
    }

    async updateScenarioObjectFromProject(scenarioObjectId) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      const object = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/objects/${scenarioObjectId}/update-from-project`, { method: 'POST' });
      scenario.objects = scenario.objects.map((item) => item.id === object.id ? object : item);
      this.invalidateTerrainView(); this.invalidateComparison(); this.emit(); return object;
    }

    async updateScenarioObject(scenarioObjectId, object) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      const result = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/objects/${scenarioObjectId}`, {
        method: 'PUT', body: JSON.stringify(object),
      });
      scenario.objects = scenario.objects.map((item) => item.id === scenarioObjectId ? result.object : item);
      this.invalidateTerrainView(); this.invalidateComparison(); this.clearError(); this.emit(); return result;
    }

    async saveScenarioObject(object) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      const result = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/objects`, { method: 'POST', body: JSON.stringify(object) });
      scenario.objects = [...scenario.objects, result.object]; this.invalidateTerrainView(); this.invalidateComparison(); this.clearError(); this.emit(); return result;
    }

    async deleteScenarioObject(scenarioObjectId) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/objects/${scenarioObjectId}`, { method: 'DELETE' });
      scenario.objects = scenario.objects.filter((item) => item.id !== scenarioObjectId);
      const nextResults = { ...this.simulationResults }; delete nextResults[scenarioObjectId]; this.simulationResults = nextResults;
      this.invalidateTerrainView(); this.invalidateComparison(); this.clearError(); this.emit();
    }

    async saveObject(object) {
      if (!this.currentProject) throw new Error('Abra ou crie primeiro um projeto.');
      try {
        const result = await this.request(`/projects/${this.currentProject.id}/objects`, {
          method: 'POST', body: JSON.stringify(object),
        });
        this.objects = [...this.objects, result.object];
        this.invalidateTerrainView(); this.clearError(); this.emit();
        return result;
      } catch (error) { this.setError(error); throw error; }
    }

    async updateObject(objectId, object) {
      const result = await this.request(`/projects/${this.currentProject.id}/objects/${objectId}`, {
        method: 'PUT', body: JSON.stringify(object),
      });
      this.objects = this.objects.map((item) => item.id === objectId ? result.object : item);
      this.invalidateTerrainView(); this.clearError(); this.emit();
      return result;
    }

    async deleteObject(objectId) {
      await this.request(`/projects/${this.currentProject.id}/objects/${objectId}`, { method: 'DELETE' });
      this.objects = this.objects.filter((item) => item.id !== objectId);
      this.invalidateTerrainView(); this.clearError(); this.emit();
    }

    async loadTerrainMesh() {
      if (!this.currentProject) throw new Error('Cria ou abre uma área de trabalho para visualizar o terreno em 3D.');
      this.terrainView = { status: 'loading', data: null, error: null };
      this.emit();
      try {
        const query = this.activeScenarioId ? `?scenario_id=${encodeURIComponent(this.activeScenarioId)}` : '';
        const data = await this.request(`/projects/${this.currentProject.id}/terrain/mesh${query}`);
        this.terrainView = { status: 'ready', data, error: null };
        this.clearError(); this.emit();
        return data;
      } catch (error) {
        this.terrainView = { status: 'error', data: null, error: error.message };
        this.setError(error);
        throw error;
      }
    }

    async previewBuildingProposal(input) {
      if (!this.currentProject) throw new Error('Abre primeiro uma área de trabalho.');
      this.planningProposal = { status: 'loading', preview: null, error: null };
      this.emit();
      try {
        const preview = await this.request(`/projects/${this.currentProject.id}/planning/building-preview`, {
          method: 'POST', body: JSON.stringify(input),
        });
        this.planningProposal = { status: 'ready', preview, error: null };
        this.clearError(); this.emit();
        return preview;
      } catch (error) {
        this.planningProposal = { status: 'error', preview: null, error: error.message };
        this.setError(error); throw error;
      }
    }

    async createGuidedBuildingProposal(input) {
      if (!this.currentProject || !this.activeScenario) throw new Error('Cria ou abre primeiro uma alternativa.');
      this.planningProposal = { ...this.planningProposal, status: 'saving', error: null };
      this.emit();
      try {
        const proposal = await this.request(`/projects/${this.currentProject.id}/scenarios/${this.activeScenario.id}/planning/building-proposal`, {
          method: 'POST', body: JSON.stringify(input),
        });
        const created = proposal.objects.map((entry) => entry.object);
        this.activeScenario.objects = [...this.activeScenario.objects, ...created];
        if (proposal.earthwork_result) {
          const result = proposal.earthwork_result;
          this.simulationResults = {
            ...this.simulationResults,
            [result.scenario_object_id]: {
              ...(this.simulationResults[result.scenario_object_id] || {}),
              [result.engine_type]: result,
            },
          };
        }
        this.planningProposal = { status: 'saved', preview: proposal, error: null };
        this.invalidateTerrainView(); this.invalidateComparison(); this.clearError(); this.emit();
        return proposal;
      } catch (error) {
        this.planningProposal = { ...this.planningProposal, status: 'error', error: error.message };
        this.setError(error); throw error;
      }
    }

    async runSimulation(scenarioObjectId, engineType) {
      if (!this.currentProject) throw new Error('Abra ou crie primeiro um projeto.');
      try {
        const scenario = this.activeScenario;
        if (!scenario) throw new Error('Crie ou abra um cenário antes de simular.');
        const scenarioObject = scenario.objects.find((item) => item.id === scenarioObjectId);
        if (!scenarioObject) throw new Error('O objeto não existe no cenário de simulação. Crie um novo cenário na Phase 3.');
        const result = await this.request('/simulations/run', {
          method: 'POST',
          body: JSON.stringify({ scenario_id: scenario.id, scenario_object_id: scenarioObject.id, engine_type: engineType }),
        });
        this.simulationResults = { ...this.simulationResults, [scenarioObject.id]: { ...(this.simulationResults[scenarioObject.id] || {}), [engineType]: result } };
        this.invalidateComparison(); this.clearError(); this.emit();
        return result;
      } catch (error) { this.setError(error); throw error; }
    }

    async runEarthwork(scenarioObjectId) {
      return this.runSimulation(scenarioObjectId, 'earthwork');
    }

    async runCultivableArea(scenarioObjectId) {
      return this.runSimulation(scenarioObjectId, 'cultivable_area');
    }

    async loadTerrainSuitability(objective = 'building') {
      if (!this.currentProject) throw new Error('Abre primeiro uma área de trabalho.');
      this.terrainSuitability = { status: 'loading', data: null, error: null };
      this.emit();
      try {
        const data = await this.request(`/projects/${this.currentProject.id}/terrain/suitability?objective=${encodeURIComponent(objective)}`);
        this.terrainSuitability = { status: 'ready', data, error: null };
        this.clearError(); this.emit();
        return data;
      } catch (error) {
        this.terrainSuitability = { status: 'error', data: null, error: error.message };
        this.setError(error); throw error;
      }
    }

    async compareScenarios(scenarioIds) {
      if (!this.currentProject) throw new Error('Abre primeiro uma área de trabalho.');
      this.comparison = { status: 'loading', data: null, error: null };
      this.emit();
      try {
        const data = await this.request(`/projects/${this.currentProject.id}/comparison`, {
          method: 'POST', body: JSON.stringify({ scenario_ids: scenarioIds }),
        });
        this.comparison = { status: 'ready', data, error: null };
        this.clearError(); this.emit();
        return data;
      } catch (error) {
        this.comparison = { status: 'error', data: null, error: error.message };
        this.setError(error); throw error;
      }
    }
  }

  window.AtlasProjectStore = ProjectStore;
  window.projectStore = new ProjectStore();
}());
