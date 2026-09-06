// Package ode talks to the PDS Geosciences Node ODE REST API
// (oderest.rsl.wustl.edu) to find and download NAC/WAC strips (and, as a
// Tier-3 bonus, Chandrayaan-1 M3 data via the same endpoint) matching a
// given footprint.
//
// Endpoint confirmed live against oderest.rsl.wustl.edu/live2/. The exact
// IHID/IID/PT values were NOT guessed — they were pulled directly from
// ODE's own self-description query:
//
//	https://oderest.rsl.wustl.edu/live2/?query=iipt&target=moon&ihid=lro&output=JSON
//
// That query returns every valid (IHID, IID, PT) combination ODE actually
// has data for. For LRO/LROC the confirmed values are:
//
//	IHID=LRO, IID=LROC, PT=EDRNAC4 (PDS4 Experiment Data Record, NAC)
//	IHID=LRO, IID=LROC, PT=EDRWAC4 (PDS4 Experiment Data Record, WAC — Color)
//
// (Older-looking codes like "EDRNAC"/"EDRWAC" without the "4" suffix don't
// exist for this target — ODE's moon holdings are PDS4, not PDS3 — and
// lowercase ihid/iid values are accepted syntactically but return
// "Invalid IIPT" since they don't match any real dataset.)
//
// If a query ever starts erroring again after ODE reprocesses/renames a
// dataset, re-run the iipt query above rather than guessing — it's the
// authoritative source of truth, and the PDF manual
// (https://oderest.rsl.wustl.edu/ODE_REST_V2.1.6.pdf) is blocked by
// robots.txt for automated fetching so it can't be cross-checked here.
// The footprint filter param names below (westernlon/easternlon/
// minlat/maxlat) are the general ODE REST convention and were accepted by
// live2 without error, but weren't separately confirmed to actually filter
// correctly — watch for that if results include products far outside your
// bbox.
package ode

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"path"
	"path/filepath"

	"lumen-backend/internal/config"
	"lumen-backend/internal/downloader"
)

const baseURL = "https://oderest.rsl.wustl.edu/live2/"

// Client wraps ODE REST queries.
type Client struct {
	HTTP   *http.Client
	OutDir string // where downloaded products land
}

// New returns a Client writing downloads under outDir.
func New(outDir string) *Client {
	return &Client{HTTP: http.DefaultClient, OutDir: outDir}
}

// Query parameters for an ODE product search. IHID/IID/PT follow ODE's
// vocabulary — confirmed real values for LRO LROC:
//
//	IHID=lro, IID=lroc, PT=EDRNAC (NAC) or PT=EDRWAC (WAC)
//	Chandrayaan-1 M3 (Tier 3 bonus only): IHID=ch1-orb, IID=m3
type QueryParams struct {
	IHID       string // instrument host id, e.g. "lro"
	IID        string // instrument id, e.g. "lroc"
	PT         string // product type, e.g. "EDRNAC" / "EDRWAC"
	BBox       config.BoundingBox
	Target     string // e.g. "moon" — ODE requires this
	Results    string // ODE "results" code, default "mbp" per documented example
	MaxResults int
}

// oderestResponse mirrors just the fields we need from ODE's JSON envelope.
type oderestResponse struct {
	ODEResults struct {
		Products struct {
			Product []Product `json:"Product"`
		} `json:"Products"`
	} `json:"ODEResults"`
}

// Product is a single ODE result: one image strip. Field names below were
// taken directly from a real response (not guessed) — see the confirmed
// sample at https://oderest.rsl.wustl.edu/live2/?query=products&target=moon
// &ihid=lro&iid=lroc&pt=EDRNAC4&results=mbp&output=JSON for a live example.
//
// Important: ODE does NOT return a direct URL for the raw data file (the
// .IMG). It only gives:
//   - LabelURL: a direct, working URL to the PDS label (.xml)
//   - FilesURL: a link to an ODE *webpage* listing files (HTML, not JSON)
//   - Product_name: the raw data file's filename, e.g. "M1163340872RE.IMG"
//
// DownloadProduct derives the data file's URL by taking LabelURL's
// directory and swapping in Product_name — confirmed working via a manual
// HEAD request against a real sample (200 OK, served from S3) before this
// was wired in. This is an inferred convention (labels and data files
// sharing a directory), not something ODE's docs state outright, so if a
// download 404s for a specific product, that assumption may not hold
// mission-wide — check FilesURL by hand for that product as a fallback.
type Product struct {
	PDSID       string `json:"pdsid"`
	ProductName string `json:"Product_name"`
	LabelURL    string `json:"LabelURL"`
	FilesURL    string `json:"FilesURL"`
	ProductURL  string `json:"ProductURL"`
}

// Query hits the ODE "product" query endpoint for the given footprint and
// instrument, returning matching products (strips).
func (c *Client) Query(p QueryParams) ([]Product, error) {
	if p.Target == "" {
		p.Target = "moon"
	}
	if p.Results == "" {
		p.Results = "mbp" // per the documented live2 example; verify against the PDF if this doesn't behave as expected
	}
	if p.MaxResults == 0 {
		p.MaxResults = 50
	}

	q := url.Values{}
	q.Set("query", "products")
	q.Set("target", p.Target)
	q.Set("ihid", p.IHID)
	q.Set("iid", p.IID)
	if p.PT != "" {
		q.Set("pt", p.PT)
	}
	q.Set("results", p.Results)
	q.Set("output", "JSON")
	// Footprint filter — TODO verify these exact param names on live2 against
	// the PDF manual; westernlon/easternlon/minlat/maxlat is the general ODE
	// REST convention but wasn't part of the confirmed example above.
	q.Set("westernlon", fmt.Sprintf("%f", p.BBox.MinLon))
	q.Set("easternlon", fmt.Sprintf("%f", p.BBox.MaxLon))
	q.Set("minlat", fmt.Sprintf("%f", p.BBox.MinLat))
	q.Set("maxlat", fmt.Sprintf("%f", p.BBox.MaxLat))
	q.Set("maxresults", fmt.Sprintf("%d", p.MaxResults))

	reqURL := baseURL + "?" + q.Encode()
	resp, err := c.HTTP.Get(reqURL)
	if err != nil {
		return nil, fmt.Errorf("ode: request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("ode: unexpected status %d from %s", resp.StatusCode, reqURL)
	}

	var parsed oderestResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return nil, fmt.Errorf("ode: decoding response: %w (ODE's JSON shape varies by query type — verify against a live response and adjust the struct if this errors)", err)
	}

	return parsed.ODEResults.Products.Product, nil
}

// DownloadProduct pulls the label file (direct URL from ODE) and the raw
// data file (derived — see the Product doc comment) into
// <OutDir>/<siteID>/<pdsid>/.
func (c *Client) DownloadProduct(siteID string, p Product) error {
	destDir := filepath.Join(c.OutDir, siteID, p.PDSID)

	if p.LabelURL != "" {
		labelDest := filepath.Join(destDir, path.Base(p.LabelURL))
		if err := c.fetchOne(labelDest, p.LabelURL, "label"); err != nil {
			return err
		}
	}

	if p.LabelURL != "" && p.ProductName != "" {
		dataURL, err := deriveDataURL(p.LabelURL, p.ProductName)
		if err != nil {
			return fmt.Errorf("ode: deriving data URL for %s: %w", p.PDSID, err)
		}
		dataDest := filepath.Join(destDir, p.ProductName)
		if err := c.fetchOne(dataDest, dataURL, "data"); err != nil {
			return fmt.Errorf("%w (derived URL may be wrong for this product — check %s by hand)", err, p.FilesURL)
		}
	}

	return nil
}

func (c *Client) fetchOne(dest, srcURL, kind string) error {
	res, err := downloader.Fetch(downloader.Options{URL: srcURL, Dest: dest, MaxRetries: 5})
	if err != nil {
		return fmt.Errorf("ode: downloading %s (%s): %w", kind, srcURL, err)
	}
	status := "downloaded"
	if res.Skipped {
		status = "already present"
	}
	fmt.Printf("  [ODE] %s (%s) -> %s (%s, %d bytes)\n", path.Base(dest), kind, dest, status, res.BytesTotal)
	return nil
}

// deriveDataURL takes a confirmed-working LabelURL and swaps in productName
// in the same directory, since ODE doesn't provide a direct data-file URL.
func deriveDataURL(labelURL, productName string) (string, error) {
	u, err := url.Parse(labelURL)
	if err != nil {
		return "", err
	}
	u.Path = path.Join(path.Dir(u.Path), productName)
	return u.String(), nil
}
