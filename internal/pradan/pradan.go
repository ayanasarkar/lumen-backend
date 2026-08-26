// Package pradan is a SCAFFOLD for pulling OHRC, TMC-2, IIRS Level-1, and
// CH2 SPICE kernels from ISSDC's PRADAN portal (pradan.issdc.gov.in/ch2/).
//
// IMPORTANT — read this before using:
// PRADAN does not (as of this writing) publish an open, documented REST API
// the way ODE does. Access is normally: register an account -> log in via
// the web portal -> browse/search by instrument+footprint in the UI ->
// download files, which typically requires an authenticated session
// (cookie or token) attached to each request.
//
// This file gives you the shape of a client so the rest of the pipeline
// (manifest format, download loop, retry/resume via the shared downloader)
// is ready to go — but the actual login/session/query logic is a TODO you
// fill in once you're registered and can see PRADAN's real request/response
// format (open browser dev tools -> Network tab while browsing PRADAN, or
// check if ISSDC has since published API docs).
//
// A pragmatic path that unblocks you TODAY without waiting on the auth flow:
// manually download the OHRC/TMC-2/IIRS files for your two sites through the
// PRADAN website, drop the resulting URLs (or local paths) into
// manifests/pradan_manifest.txt, and use ManifestDownload below — same
// pattern as the DEM/SPICE connectors. Swap in the real client once you've
// reverse-engineered the auth flow.
package pradan

import (
	"bufio"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"lumen-backend/internal/downloader"
)

// Client is a placeholder for an authenticated PRADAN session.
type Client struct {
	HTTP      *http.Client
	SessionID string // TODO: populate this from a real login call
	OutDir    string
}

// New returns an unauthenticated Client. Call Login before Query/Download.
func New(outDir string) *Client {
	return &Client{HTTP: &http.Client{}, OutDir: outDir}
}

// Login is UNIMPLEMENTED. PRADAN's auth flow isn't publicly documented, so
// this is a stub describing what needs to happen:
//  1. POST username/password to PRADAN's login endpoint (find the exact URL
//     + form fields via browser dev tools while logging in manually).
//  2. Capture the session cookie/token from the response.
//  3. Store it on c.SessionID / in c.HTTP's cookie jar for subsequent
//     requests.
func (c *Client) Login(username, password string) error {
	return fmt.Errorf("pradan: Login is not implemented — PRADAN has no documented public API; " +
		"inspect the portal's login request in your browser's dev tools and fill this in, " +
		"or use ManifestDownload with manually-obtained URLs in the meantime")
}

// Query is UNIMPLEMENTED for the same reason as Login. Once you know the
// real search endpoint + params (instrument, footprint, date range), wire
// it up here following the same pattern as internal/ode.Query.
func (c *Client) Query(instrument string, siteID string) error {
	return fmt.Errorf("pradan: Query is not implemented — see package doc comment for the manual-download fallback")
}

// ManifestDownload reads a plain-text manifest (one URL per line, blank
// lines and "#" comments ignored) and downloads each file into
// <OutDir>/<siteID>/. This is the practical way to pull PRADAN data today:
// download manually via the browser once, paste the resulting direct file
// URLs into manifests/pradan_manifest.txt (or wherever authenticated
// download links land), and let this handle retries/resume.
func (c *Client) ManifestDownload(siteID, manifestPath string) error {
	f, err := os.Open(manifestPath)
	if err != nil {
		return fmt.Errorf("pradan: opening manifest %s: %w", manifestPath, err)
	}
	defer f.Close()

	destDir := filepath.Join(c.OutDir, siteID)
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
			return fmt.Errorf("pradan: downloading %s: %w", line, err)
		}
		status := "downloaded"
		if res.Skipped {
			status = "already present"
		}
		fmt.Printf("  [PRADAN] %s -> %s (%s, %d bytes)\n", fileName, dest, status, res.BytesTotal)
		count++
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("pradan: reading manifest: %w", err)
	}
	if count == 0 {
		fmt.Printf("  [PRADAN] manifest %s is empty — add PRADAN file URLs before running this connector\n", manifestPath)
	}
	return nil
}
