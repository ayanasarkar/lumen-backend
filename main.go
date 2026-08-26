// Command lumen-backend is the unified ingestion CLI for the LUMEN demo
// pipeline. It drives all required connectors: PRADAN, ODE, DEM, SPICE, and
// the Robbins Crater DB (Tier 1 + Tier 2 from the dataset access guide).
//
// Usage:
//
//	lumen-backend all                  # run every required connector, in order
//	lumen-backend ode                  # ODE only (both sites)
//	lumen-backend pradan                # PRADAN only (manifest-driven for now)
//	lumen-backend dem                  # DEM only (manifest-driven)
//	lumen-backend spice                # SPICE generic + LRO kernels
//	lumen-backend robbins              # Robbins Crater DB (one-time)
//
// Flags:
//
//	-sites string     path to sites.json (default "sites.json")
//	-data string      output data directory (default "data")
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"strings"

	"lumen-backend/internal/config"
	"lumen-backend/internal/dem"
	"lumen-backend/internal/ode"
	"lumen-backend/internal/pradan"
	"lumen-backend/internal/robbins"
	"lumen-backend/internal/spice"
)

func main() {
	sitesPath := flag.String("sites", "sites.json", "path to sites.json")
	dataDir := flag.String("data", "data", "output data directory")
	flag.Parse()

	args := flag.Args()
	if len(args) == 0 {
		printUsage()
		os.Exit(1)
	}
	cmd := args[0]

	cfg, err := config.Load(*sitesPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}

	var runErr error
	switch cmd {
	case "all":
		runErr = runAll(cfg, *dataDir)
	case "ode":
		runErr = runODE(cfg, *dataDir)
	case "pradan":
		runErr = runPradan(cfg, *dataDir)
	case "dem":
		runErr = runDEM(cfg, *dataDir)
	case "spice":
		runErr = runSPICE(*dataDir)
	case "robbins":
		runErr = robbins.Fetch(*dataDir)
	default:
		printUsage()
		os.Exit(1)
	}

	if runErr != nil {
		fmt.Fprintln(os.Stderr, "error:", runErr)
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println(`lumen-backend — LUMEN dataset ingestion CLI

Usage:
  lumen-backend [flags] <command>

Commands:
  all       Run every required connector (PRADAN, ODE, DEM, SPICE, Robbins)
  ode       Query + download matching NAC/WAC strips from ODE
  pradan    Download PRADAN files (manifest-driven — see internal/pradan doc)
  dem       Download DEM tiles from a manifest (SLDEM2015 / PGDA)
  spice     Download generic + LRO SPICE kernels
  robbins   Download the Robbins Crater DB (one-time)

Flags:
  -sites string   path to sites.json (default "sites.json")
  -data string    output data directory (default "data")

First-time setup:
  cp sites.example.json sites.json
  # edit sites.json with your two chosen footprints
  lumen-backend all`)
}

func runAll(cfg *config.Config, dataDir string) error {
	steps := []struct {
		name string
		fn   func() error
	}{
		{"PRADAN", func() error { return runPradan(cfg, dataDir) }},
		{"ODE", func() error { return runODE(cfg, dataDir) }},
		{"DEM", func() error { return runDEM(cfg, dataDir) }},
		{"SPICE", func() error { return runSPICE(dataDir) }},
		{"Robbins", func() error { return robbins.Fetch(dataDir) }},
	}
	for _, s := range steps {
		fmt.Printf("== %s ==\n", s.name)
		if err := s.fn(); err != nil {
			// Keep going even if one connector fails (e.g. PRADAN manifest
			// not filled in yet) so a single missing piece doesn't block
			// everything else.
			fmt.Fprintf(os.Stderr, "  [%s] error: %v\n", s.name, err)
		}
	}
	return nil
}

func runODE(cfg *config.Config, dataDir string) error {
	client := ode.New(dataDir + "/ode")
	for _, siteType := range []config.SiteType{config.Equatorial, config.Polar} {
		site, err := cfg.Get(siteType)
		if err != nil {
			return err
		}
		fmt.Printf("  querying ODE for site %s (%s)...\n", site.ID, site.Name)
		for _, instrument := range []struct{ ihid, iid, pt, label string }{
			{"LRO", "LROC", "EDRNAC4", "NAC"},
			{"LRO", "LROC", "EDRWAC4", "WAC"},
		} {
			products, err := client.Query(ode.QueryParams{
				IHID: instrument.ihid,
				IID:  instrument.iid,
				PT:   instrument.pt,
				BBox: site.BBox,
			})
			if err != nil {
				return fmt.Errorf("ode query (%s/%s/%s) for site %s: %w", instrument.ihid, instrument.iid, instrument.pt, site.ID, err)
			}
			fmt.Printf("  found %d %s products for %s\n", len(products), instrument.label, site.ID)
			for _, p := range products {
				if err := client.DownloadProduct(site.ID, p); err != nil {
					return err
				}
			}
		}
	}
	return nil
}

func runPradan(cfg *config.Config, dataDir string) error {
	client := pradan.New(dataDir + "/pradan")
	for _, siteType := range []config.SiteType{config.Equatorial, config.Polar} {
		site, err := cfg.Get(siteType)
		if err != nil {
			return err
		}
		if err := client.ManifestDownload(site.ID, "manifests/pradan_manifest.txt"); err != nil {
			return err
		}
	}
	return nil
}

func runDEM(cfg *config.Config, dataDir string) error {
	for _, siteType := range []config.SiteType{config.Equatorial, config.Polar} {
		site, err := cfg.Get(siteType)
		if err != nil {
			return err
		}
		if err := dem.ManifestDownload(site.ID, dataDir+"/dem", "manifests/dem_manifest.txt"); err != nil {
			return err
		}
	}
	return nil
}

func runSPICE(dataDir string) error {
	outDir := dataDir + "/spice"
	if err := spice.FetchGenericKernels(outDir); err != nil {
		return err
	}
	// LRO-specific kernel URLs go in manifests/spice_lro_manifest.txt —
	// pick the ones covering your imagery's acquisition dates.
	urls, err := readManifest("manifests/spice_lro_manifest.txt")
	if err != nil {
		return err
	}
	return spice.FetchLROKernels(outDir, urls)
}

func readManifest(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()

	var urls []string
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		urls = append(urls, line)
	}
	return urls, scanner.Err()
}
