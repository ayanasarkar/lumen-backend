// Package robbins downloads the Robbins Lunar Crater Database (2018/2019),
// a single static file — no per-site querying needed since it covers the
// whole Moon and gets filtered by footprint downstream (e.g. in the
// GET /sites/{id}/craters endpoint or MatchMetrics' RMSE check).
package robbins

import (
	"fmt"
	"path/filepath"

	"lumen-backend/internal/downloader"
)

// URL is the direct download link from USGS Astropedia.
const URL = "https://astropedia.astrogeology.usgs.gov/download/Moon/Research/Craters/lunar_crater_database_robbins_2018.zip"

// Fetch downloads the Robbins database into <outDir>/robbins/. Safe to call
// repeatedly — already-downloaded data is skipped.
func Fetch(outDir string) error {
	dest := filepath.Join(outDir, "robbins", filepath.Base(URL))
	res, err := downloader.Fetch(downloader.Options{URL: URL, Dest: dest, MaxRetries: 5})
	if err != nil {
		return fmt.Errorf("robbins: %w (if this URL 404s, the exact filename/extension on Astropedia may have changed — check the page and update robbins.URL)", err)
	}
	status := "downloaded"
	if res.Skipped {
		status = "already present"
	}
	fmt.Printf("  [Robbins] -> %s (%s, %d bytes)\n", dest, status, res.BytesTotal)
	return nil
}
