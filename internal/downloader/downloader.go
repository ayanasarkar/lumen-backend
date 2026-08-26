// Package downloader provides a single, reusable file-fetching core used by
// every LUMEN connector (ODE, PRADAN, DEM, SPICE, Robbins). Centralizing this
// logic means every connector gets resume support, retries with backoff, and
// checksum verification for free instead of reimplementing it five times.
package downloader

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

// Options controls how a single download is performed.
type Options struct {
	URL string // source URL
	// Dest is the final path the file should end up at. A ".part" sibling
	// file is used while the download is in progress so a crash never
	// leaves behind a file that looks complete but isn't.
	Dest string
	// SHA256 is optional. If non-empty, the downloaded file's checksum is
	// verified after completion and an error is returned on mismatch.
	SHA256 string
	// MaxRetries is how many times to retry a failed/interrupted download
	// before giving up. Each retry backs off exponentially.
	MaxRetries int
	// Client lets callers inject a custom *http.Client (timeouts, auth
	// transport, etc). If nil, a sane default is used.
	Client *http.Client
}

// Result summarizes what happened for logging/CLI output.
type Result struct {
	Dest       string
	BytesTotal int64
	Skipped    bool // true if the file already existed and was valid
	Resumed    bool // true if a partial ".part" file was resumed
}

const defaultTimeout = 30 * time.Minute

// Fetch downloads a single file per Options, with resume + retry + optional
// checksum verification. It is idempotent: calling it again after a
// completed download is a fast no-op (unless the checksum doesn't match, in
// which case it re-downloads).
func Fetch(opt Options) (*Result, error) {
	if opt.URL == "" || opt.Dest == "" {
		return nil, fmt.Errorf("downloader: URL and Dest are required")
	}
	if opt.MaxRetries <= 0 {
		opt.MaxRetries = 5
	}
	client := opt.Client
	if client == nil {
		client = &http.Client{Timeout: defaultTimeout}
	}

	if err := os.MkdirAll(filepath.Dir(opt.Dest), 0o755); err != nil {
		return nil, fmt.Errorf("downloader: creating dest dir: %w", err)
	}

	// Already-complete and checksum-valid file? Skip entirely.
	if info, err := os.Stat(opt.Dest); err == nil && !info.IsDir() {
		if opt.SHA256 == "" || verifyChecksum(opt.Dest, opt.SHA256) == nil {
			return &Result{Dest: opt.Dest, BytesTotal: info.Size(), Skipped: true}, nil
		}
		// Checksum mismatch on an existing file: remove and re-fetch.
		_ = os.Remove(opt.Dest)
	}

	partPath := opt.Dest + ".part"
	var lastErr error
	resumed := false

	for attempt := 0; attempt <= opt.MaxRetries; attempt++ {
		if attempt > 0 {
			backoff := time.Duration(1<<uint(attempt)) * time.Second
			if backoff > 30*time.Second {
				backoff = 30 * time.Second
			}
			time.Sleep(backoff)
		}

		var startOffset int64
		if info, err := os.Stat(partPath); err == nil {
			startOffset = info.Size()
			if startOffset > 0 {
				resumed = true
			}
		}

		req, err := http.NewRequest(http.MethodGet, opt.URL, nil)
		if err != nil {
			return nil, fmt.Errorf("downloader: building request: %w", err)
		}
		if startOffset > 0 {
			req.Header.Set("Range", fmt.Sprintf("bytes=%d-", startOffset))
		}

		resp, err := client.Do(req)
		if err != nil {
			lastErr = err
			continue
		}

		if resp.StatusCode == http.StatusRequestedRangeNotSatisfiable {
			// Server disagrees the partial file is valid; start over.
			resp.Body.Close()
			_ = os.Remove(partPath)
			startOffset = 0
			lastErr = fmt.Errorf("range not satisfiable, restarting")
			continue
		}
		if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
			resp.Body.Close()
			lastErr = fmt.Errorf("unexpected status %d for %s", resp.StatusCode, opt.URL)
			continue
		}

		flags := os.O_CREATE | os.O_WRONLY
		if resp.StatusCode == http.StatusPartialContent {
			flags |= os.O_APPEND
		} else {
			// Server ignored our Range header and is sending the whole
			// file from byte 0 — truncate any stale partial data.
			flags |= os.O_TRUNC
			startOffset = 0
		}

		f, err := os.OpenFile(partPath, flags, 0o644)
		if err != nil {
			resp.Body.Close()
			return nil, fmt.Errorf("downloader: opening part file: %w", err)
		}

		written, copyErr := io.Copy(f, resp.Body)
		f.Close()
		resp.Body.Close()

		if copyErr != nil {
			lastErr = fmt.Errorf("downloader: copy interrupted: %w", copyErr)
			continue
		}

		_ = written
		// Success: move .part -> final destination.
		if err := os.Rename(partPath, opt.Dest); err != nil {
			return nil, fmt.Errorf("downloader: finalizing file: %w", err)
		}

		if opt.SHA256 != "" {
			if err := verifyChecksum(opt.Dest, opt.SHA256); err != nil {
				return nil, fmt.Errorf("downloader: checksum failed for %s: %w", opt.Dest, err)
			}
		}

		info, _ := os.Stat(opt.Dest)
		var total int64
		if info != nil {
			total = info.Size()
		}
		return &Result{Dest: opt.Dest, BytesTotal: total, Resumed: resumed}, nil
	}

	return nil, fmt.Errorf("downloader: giving up on %s after %d attempts: %w", opt.URL, opt.MaxRetries+1, lastErr)
}

func verifyChecksum(path, want string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return err
	}
	got := hex.EncodeToString(h.Sum(nil))
	if got != want {
		return fmt.Errorf("checksum mismatch: want %s, got %s", want, got)
	}
	return nil
}
