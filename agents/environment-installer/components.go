package main

type RequiredComponent struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type ComponentHealth struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Status string `json:"status"`
}

func requiredComponentsHealthy(required []RequiredComponent, reported []ComponentHealth) bool {
	if len(required) != len(reported) {
		return false
	}
	seen := make(map[string]bool, len(reported))
	for _, component := range reported {
		if component.Status != "healthy" || seen[component.ID] {
			return false
		}
		seen[component.ID] = true
	}
	for _, component := range required {
		if !seen[component.ID] {
			return false
		}
	}
	return true
}
