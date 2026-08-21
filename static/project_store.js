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
      this.uiState = {
        sidebarCollapsed: false,
        activeWorkspaceView: 'explore',
        contextPanelOpen: false,
        objectComposerOpen: false,
        selectedObjectId: null,
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

    async createProject(name, baseParcel) {
      try {
        const project = await this.request('/projects', {
          method: 'POST', body: JSON.stringify({ name, base_parcel: baseParcel }),
        });
        this.currentProject = project;
        this.baseParcel = project.base_parcel;
        this.objects = [];
        this.scenarios = []; this.activeScenarioId = null; this.simulationResults = {};
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
        this.clearError(); this.emit();
        return scenario;
      } catch (error) { this.setError(error); throw error; }
    }

    get activeScenario() { return this.scenarios.find((scenario) => scenario.id === this.activeScenarioId) || null; }

    async duplicateScenario(name) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      const duplicate = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/duplicate`, { method: 'POST', body: JSON.stringify({ name }) });
      this.scenarios = [...this.scenarios, duplicate]; this.activeScenarioId = duplicate.id; this.simulationResults = {}; this.emit();
      return duplicate;
    }

    async updateScenarioObjectFromProject(scenarioObjectId) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      const object = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/objects/${scenarioObjectId}/update-from-project`, { method: 'POST' });
      scenario.objects = scenario.objects.map((item) => item.id === object.id ? object : item);
      this.emit(); return object;
    }

    async updateScenarioObject(scenarioObjectId, object) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      const result = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/objects/${scenarioObjectId}`, {
        method: 'PUT', body: JSON.stringify(object),
      });
      scenario.objects = scenario.objects.map((item) => item.id === scenarioObjectId ? result.object : item);
      this.clearError(); this.emit(); return result;
    }

    async saveScenarioObject(object) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      const result = await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/objects`, { method: 'POST', body: JSON.stringify(object) });
      scenario.objects = [...scenario.objects, result.object]; this.clearError(); this.emit(); return result;
    }

    async deleteScenarioObject(scenarioObjectId) {
      const scenario = this.activeScenario;
      if (!scenario) throw new Error('Abra primeiro um cenário.');
      await this.request(`/projects/${this.currentProject.id}/scenarios/${scenario.id}/objects/${scenarioObjectId}`, { method: 'DELETE' });
      scenario.objects = scenario.objects.filter((item) => item.id !== scenarioObjectId);
      const nextResults = { ...this.simulationResults }; delete nextResults[scenarioObjectId]; this.simulationResults = nextResults;
      this.clearError(); this.emit();
    }

    async saveObject(object) {
      if (!this.currentProject) throw new Error('Abra ou crie primeiro um projeto.');
      try {
        const result = await this.request(`/projects/${this.currentProject.id}/objects`, {
          method: 'POST', body: JSON.stringify(object),
        });
        this.objects = [...this.objects, result.object];
        this.clearError(); this.emit();
        return result;
      } catch (error) { this.setError(error); throw error; }
    }

    async updateObject(objectId, object) {
      const result = await this.request(`/projects/${this.currentProject.id}/objects/${objectId}`, {
        method: 'PUT', body: JSON.stringify(object),
      });
      this.objects = this.objects.map((item) => item.id === objectId ? result.object : item);
      this.clearError(); this.emit();
      return result;
    }

    async deleteObject(objectId) {
      await this.request(`/projects/${this.currentProject.id}/objects/${objectId}`, { method: 'DELETE' });
      this.objects = this.objects.filter((item) => item.id !== objectId);
      this.clearError(); this.emit();
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
        this.clearError(); this.emit();
        return result;
      } catch (error) { this.setError(error); throw error; }
    }

    async runEarthwork(scenarioObjectId) {
      return this.runSimulation(scenarioObjectId, 'earthwork');
    }

    async runCultivableArea(scenarioObjectId) {
      return this.runSimulation(scenarioObjectId, 'cultivable_area');
    }
  }

  window.AtlasProjectStore = ProjectStore;
  window.projectStore = new ProjectStore();
}());
