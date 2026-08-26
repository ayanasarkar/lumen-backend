// Package ode talks to the PDS Geosciences Node ODE REST API
// (oderest.rsl.wustl.edu) to find and download NAC/WAC strips (and, as a
// Tier-3 bonus, Chandrayaan-1 M3 data via the same endpoint) matching a
// given footprint.
//
// API reference: https://oderest.rsl.wustl.edu/ODE_REST_V2.1.pdf
// This client covers the "product" query used to list files for a
// footprint + instrument, then fetches the product files themselves.
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

const baseURL = "https://oderest.rsl.wustl.edu/livegds/"

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
// vocabulary, e.g.:
//
//	Equatorial LRO NAC:  IHID=LRO-L-LROC, IID=NAC, PT=EDR
//	LRO WAC:             IHID=LRO-L-LROC, IID=WAC, PT=EDR
//	Chandrayaan-1 M3:    IHID=CH1-ORB,   IID=M3,  PT=RDN (Tier 3 bonus only)
type QueryParams struct {
	IHID       string // instrument host id
	IID        string // instrument id
	PT         string // product type
	BBox       config.BoundingBox
	Target     string // e.g. "moon" — ODE requires this
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
	if p.MaxResults == 0 {
		p.MaxResults = 50
	}

	q := url.Values{}
	q.Set("target", p.Target)
	q.Set("ihid", p.IHID)
	q.Set("iid", p.IID)
	if p.PT != "" {
		q.Set("pt", p.PT)
	}
	q.Set("output", "JSON")
	q.Set("query", "product")
	// ODE's footprint filter: westernlon/easternlon/minlat/maxlat.
	q.Set("westernlon", fmt.Sprintf("%f", p.BBox.MinLon))
	q.Set("easternlon", fmt.Sprintf("%f", p.BBox.MaxLon))
	q.Set("minlat", fmt.Sprintf("%f", p.BBox.MinLat))
	q.Set("maxlat", fmt.Sprintf("%f", p.BBox.MaxLat))
	q.Set("results", fmt.Sprintf("%d", p.MaxResults))

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
