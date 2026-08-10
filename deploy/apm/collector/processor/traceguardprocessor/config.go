package traceguardprocessor

import (
	"errors"
	"regexp"
)

var regionIDPattern = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

type Config struct {
	CloudRegionID     string `mapstructure:"cloud_region_id"`
	MaxResourceAttrs  int    `mapstructure:"max_resource_attributes"`
	MaxScopeAttrs     int    `mapstructure:"max_scope_attributes"`
	MaxSpanAttrs      int    `mapstructure:"max_span_attributes"`
	MaxEventAttrs     int    `mapstructure:"max_event_attributes"`
	MaxLinkAttrs      int    `mapstructure:"max_link_attributes"`
	MaxAttributeRunes int    `mapstructure:"max_attribute_runes"`
}

func (cfg *Config) Validate() error {
	if !regionIDPattern.MatchString(cfg.CloudRegionID) {
		return errors.New("cloud_region_id must contain only letters, numbers, underscores or hyphens")
	}
	for _, value := range []int{
		cfg.MaxResourceAttrs,
		cfg.MaxScopeAttrs,
		cfg.MaxSpanAttrs,
		cfg.MaxEventAttrs,
		cfg.MaxLinkAttrs,
		cfg.MaxAttributeRunes,
	} {
		if value <= 0 {
			return errors.New("all trace guard limits must be positive")
		}
	}
	return nil
}
