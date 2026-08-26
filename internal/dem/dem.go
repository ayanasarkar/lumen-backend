// Package dem downloads Digital Elevation Models: SLDEM2015 for the
// equatorial site and a PGDA 5m/px DEM for the polar site, plus a no-auth
// Kaguya TC DTM fallback via public AWS S3 access.
package dem

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"lumen-backend/internal/downloader"
)

// ManifestDownload reads one URL per line from manifestPath (blank lines and
// "#" comments ignored) and downloads each into <outDir>/<siteID>/.
// SLDEM2015 and PGDA tiles are both plain static files, so this simple
// manifest approach covers both — find the exact tile URLs for your
// footprint on the PGDA / USGS Astropedia site and paste them in.
func ManifestDownload(siteID, outDir, manifestPath string) error {
	f, err := os.Open(manifestPath)
	if err != nil {
		return fmt.Errorf("dem: opening manifest %s: %w", manifestPath, err)
	}
	defer f.Close()

	destDir := filepath.Join(outDir, siteID)
	scanner := bufio.NewScanner(f)
	count := 0
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		fileName := filepath.Base(line)
		dest := filepath.Join(destDir, fileName)
		res, err := downloader.Fetch(downloader.Options{URL: line, Dest: dest, MaxRetries: 5})
		if err != nil {
			return fmt.Errorf("dem: downloading %s: %w", line, err)
		}
		status := "downloaded"
		if res.Skipped {
			status = "already present"
		}
		fmt.Printf("  [DEM] %s -> %s (%s, %d bytes)\n", fileName, dest, status, res.BytesTotal)
		count++
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("dem: reading manifest: %w", err)
	}
	if count == 0 {
		fmt.Printf("  [DEM] manifest %s is empty — add SLDEM2015/PGDA tile URLs before running this connector\n", manifestPath)
	}
	return nil
}

// KaguyaFallback shells out to the AWS CLI to pull a Kaguya TC DTM tile with
// no-sign-request (public bucket, no AWS account needed). Requires the
// `aws` CLI to be installed and on PATH.
//
// s3Path should look like "s3://bucket-name/path/to/tile.tif" — check the
// current public bucket name/layout on USGS's Kaguya TC DTM documentation
// page, since public bucket paths can change over time.
func KaguyaFallback(s3Path, destDir string) error {
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return fmt.Errorf("dem: creating dest dir: %w", err)
	}
	if _, err := exec.LookPath("aws"); err != nil {
		return fmt.Errorf("dem: aws CLI not found on PATH — install it (`pip install awscli` or your package manager) to use the Kaguya fallback")
	}

	cmd := exec.Command("aws", "s3", "cp", s3Path, destDir, "--no-sign-request", "--recursive")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("dem: aws s3 cp failed: %w", err)
	}
	return nil
}
