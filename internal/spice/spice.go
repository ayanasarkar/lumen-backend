// Package spice downloads NAIF SPICE kernels needed for PRISM's Sun-angle
// and viewpoint geometry: the generic kernels (leap seconds, planetary
// ephemerides — pulled once, not per-site) and the LRO-specific kernel
// archive (also generally a one-time pull covering the mission timespan,
// not per-site).
package spice

import (
	"fmt"
	"path/filepath"

	"lumen-backend/internal/downloader"
)

// GenericKernel is one file from NAIF's generic_kernels tree.
type GenericKernel struct {
	Name string // e.g. "naif0012.tls"
	URL  string // full NAIF URL
}

// DefaultGenericKernels lists the handful of generic kernels PRISM
// typically needs (leapseconds + a planetary ephemeris). Verify these are
// still the current recommended files on NAIF's site before relying on
// them long-term — NAIF periodically publishes newer leapsecond/ephemeris
// versions.
var DefaultGenericKernels = []GenericKernel{
	{Name: "naif0012.tls", URL: "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls"},
	{Name: "de440s.bsp", URL: "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp"},
	{Name: "pck00011.tpc", URL: "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc"},
}

// FetchGenericKernels pulls the standard generic kernel set into
// <outDir>/generic/. Safe to call repeatedly — already-downloaded kernels
// are skipped.
func FetchGenericKernels(outDir string) error {
	destDir := filepath.Join(outDir, "generic")
	for _, k := range DefaultGenericKernels {
		dest := filepath.Join(destDir, k.Name)
		res, err := downloader.Fetch(downloader.Options{URL: k.URL, Dest: dest, MaxRetries: 5})
		if err != nil {
			return fmt.Errorf("spice: fetching generic kernel %s: %w", k.Name, err)
		}
		status := "downloaded"
		if res.Skipped {
			status = "already present"
		}
		fmt.Printf("  [SPICE/generic] %s -> %s (%s, %d bytes)\n", k.Name, dest, status, res.BytesTotal)
	}
	return nil
}

// FetchLROKernels reads a manifest of LRO-specific kernel URLs (from the LRO
// SPICE kernel archive on NAIF or PDS) and downloads them into
// <outDir>/lro/. LRO's archive has many kernels covering different mission
// phases — pick the ones covering your imagery's acquisition dates rather
// than pulling the entire archive.
func FetchLROKernels(outDir string, urls []string) error {
	destDir := filepath.Join(outDir, "lro")
	for _, u := range urls {
		fileName := filepath.Base(u)
		dest := filepath.Join(destDir, fileName)
		res, err := downloader.Fetch(downloader.Options{URL: u, Dest: dest, MaxRetries: 5})
		if err != nil {
			return fmt.Errorf("spice: fetching LRO kernel %s: %w", fileName, err)
		}
		status := "downloaded"
		if res.Skipped {
			status = "already present"
		}
		fmt.Printf("  [SPICE/LRO] %s -> %s (%s, %d bytes)\n", fileName, dest, status, res.BytesTotal)
	}
	return nil
}
