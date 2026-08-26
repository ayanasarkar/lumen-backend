// Package ode talks to the PDS Geosciences Node ODE REST API
// (oderest.rsl.wustl.edu) to find and download NAC/WAC strips (and, as a
// Tier-3 bonus, Chandrayaan-1 M3 data via the same endpoint) matching a
// given footprint.
//
// Endpoint + ihid/iid/pt confirmed against a real documented example
// (NASA PDS API - LROC Update, topcoder.com/challenges/30045126):
//
//	http://oderest.rsl.wustl.edu/live2/?query=products&target=moon&results=mbp
//	    &ihid=lro&iid=lroc&pt=<PT>&output=JSON
//
// Full manual: https://oderest.rsl.wustl.edu/ODE_REST_V2.1.6.pdf (blocked by
// robots.txt for automated fetching, so it couldn't be verified line-by-line
// here — if a query 404s or the JSON shape doesn't decode, check the PDF and
// adjust this file, particularly the footprint filter param names below,
// which are a best-effort based on the general ODE REST convention rather
// than a confirmed live2-specific example.
package ode

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
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

// Product is a single ODE result: one image strip with its metadata + files.
type Product struct {
	PDSID         string `json:"pdsid"`
	ProductID     string `json:"ode_id"`
	Product_files struct {
		Product_file []ProductFile `json:"Product_file"`
	} `json:"Product_files"`
}

// ProductFile is one downloadable file belonging to a Product (e.g. the IMG,
// the LBL label, a browse JPEG).
type ProductFile struct {
	FileName    string `json:"FileName"`
	URL         string `json:"URL"`
	Description string `json:"Description"`
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

// DownloadProduct pulls every file belonging to one Product into
// <OutDir>/<siteID>/<pdsid>/.
func (c *Client) DownloadProduct(siteID string, p Product) error {
	destDir := filepath.Join(c.OutDir, siteID, p.PDSID)
	for _, f := range p.Product_files.Product_file {
		if f.URL == "" {
			continue
		}
		dest := filepath.Join(destDir, f.FileName)
		res, err := downloader.Fetch(downloader.Options{
			URL:        f.URL,
			Dest:       dest,
			MaxRetries: 5,
		})
		if err != nil {
			return fmt.Errorf("ode: downloading %s: %w", f.FileName, err)
		}
		status := "downloaded"
		if res.Skipped {
			status = "already present"
		}
		fmt.Printf("  [ODE] %s -> %s (%s, %d bytes)\n", f.FileName, dest, status, res.BytesTotal)
	}
	return nil
}
