// Package config holds the two site definitions (one equatorial, one polar)
// that every connector needs. Everything downstream — PRADAN, ODE, DEM —
// keys off these footprints, so this is the one file to edit first.
package config

import (
	"encoding/json"
	"fmt"
	"os"
)

// SiteType distinguishes the two required demo sites.
type SiteType string

const (
	Equatorial SiteType = "equatorial"
	Polar      SiteType = "polar"
)

// BoundingBox is a simple lat/lon footprint in degrees.
// MinLat/MaxLat: -90..90. MinLon/MaxLon: -180..180 (or 0..360, be consistent
// with whatever convention ODE/PRADAN expect for your site — see README).
type BoundingBox struct {
	MinLat float64 `json:"min_lat"`
	MaxLat float64 `json:"max_lat"`
	MinLon float64 `json:"min_lon"`
	MaxLon float64 `json:"max_lon"`
}

// Site is one of the two demo footprints.
type Site struct {
	ID    string      `json:"id"`
	Type  SiteType    `json:"type"`
	Name  string      `json:"name"`
	BBox  BoundingBox `json:"bbox"`
	Notes string      `json:"notes,omitempty"`
}

// Config is the top-level sites.json shape.
type Config struct {
	Sites []Site `json:"sites"`
}

// Load reads and validates a sites.json file. It errors loudly if the two
// required sites (one equatorial, one polar) aren't both present, since
// every later pipeline stage assumes exactly that.
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("config: reading %s: %w (have you copied sites.example.json to sites.json and filled it in?)", path, err)
	}

	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("config: parsing %s: %w", path, err)
	}

	var hasEq, hasPolar bool
	for _, s := range cfg.Sites {
		switch s.Type {
		case Equatorial:
			hasEq = true
		case Polar:
			hasPolar = true
		}
	}
	if !hasEq || !hasPolar {
		return nil, fmt.Errorf("config: sites.json must define exactly one %q site and one %q site (got %d sites)", Equatorial, Polar, len(cfg.Sites))
	}

	return &cfg, nil
}

// Get returns the site of the given type, or an error if not found.
func (c *Config) Get(t SiteType) (Site, error) {
	for _, s := range c.Sites {
		if s.Type == t {
			return s, nil
		}
	}
	return Site{}, fmt.Errorf("config: no site of type %q defined", t)
}
