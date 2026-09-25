// Package mockdata provides 10 hardcoded, randomizable results that stand in
// for a full lumen-backend pipeline run (PRADAN + ODE + DEM + SPICE + Robbins
// Crater DB combined) -- useful for local dev/demo when live API access isn't
// available (e.g. PRADAN has no public API yet, or you're offline).
package mockdata

import (
	"math/rand"
	"time"
)

// SiteResult is one candidate site with a plausible value from each dataset.
type SiteResult struct {
	ID        string  `json:"id"`
	SiteType  string  `json:"site_type"` // "equatorial" or "polar"
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`

	// PRADAN (ISSDC / Chandrayaan-2 OHRC) -- portal has no public API,
	// so this is a stand-in product ID in ISSDC's naming style.
	PradanImageID string `json:"pradan_image_id"`

	// ODE (LRO NAC/WAC)
	ODEProductID string  `json:"ode_product_id"`
	ODEImageURL  string  `json:"ode_image_url"`
	ResolutionM  float64 `json:"resolution_m_per_px"`

	// DEM (SLDEM2015 / PGDA tile)
	DEMTile string `json:"dem_tile"`

	// SPICE kernel relevant to this acquisition
	SPICEKernel string `json:"spice_kernel"`

	// Robbins Lunar Crater Database
	CraterID   string  `json:"crater_id"`
	DiameterKm float64 `json:"diameter_km"`
}

// mockPool holds the 10 hardcoded entries: 5 equatorial, 5 polar.
var mockPool = []SiteResult{
	{ID: "site-001", SiteType: "equatorial", Latitude: 5.20, Longitude: 23.40,
		PradanImageID: "ch2_ohr_ncp_20240315T0231159159_d_img_d18",
		ODEProductID: "M1303619392RE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1303619392RE.IMG",
		ResolutionM: 0.52, DEMTile: "SLDEM2015_512_00N_10N_000_045", SPICEKernel: "moon_pa_de440_200625.bpc",
		CraterID: "LU_00010234", DiameterKm: 1.8},
	{ID: "site-002", SiteType: "equatorial", Latitude: -3.10, Longitude: 118.70,
		PradanImageID: "ch2_ohr_ncp_20240402T1147032211_d_img_d21",
		ODEProductID: "M1175057718LE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1175057718LE.IMG",
		ResolutionM: 0.48, DEMTile: "SLDEM2015_512_10S_00S_090_135", SPICEKernel: "lro_frames_2024_v01.tf",
		CraterID: "LU_00048821", DiameterKm: 6.3},
	{ID: "site-003", SiteType: "equatorial", Latitude: 1.80, Longitude: 200.20,
		PradanImageID: "ch2_ohr_ncp_20240518T0912441098_d_img_d09",
		ODEProductID: "M1287744190RE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1287744190RE.IMG",
		ResolutionM: 1.02, DEMTile: "SLDEM2015_512_00N_10N_180_225", SPICEKernel: "moon_080317.tf",
		CraterID: "LU_00072310", DiameterKm: 3.1},
	{ID: "site-004", SiteType: "equatorial", Latitude: -7.40, Longitude: 305.90,
		PradanImageID: "ch2_ohr_ncp_20240601T0355128843_d_img_d14",
		ODEProductID: "M1150883125LE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1150883125LE.IMG",
		ResolutionM: 0.55, DEMTile: "SLDEM2015_512_10S_00S_270_315", SPICEKernel: "de440s.bsp",
		CraterID: "LU_00019987", DiameterKm: 0.9},
	{ID: "site-005", SiteType: "equatorial", Latitude: 0.50, Longitude: 45.00,
		PradanImageID: "ch2_ohr_ncp_20240622T1523097765_d_img_d02",
		ODEProductID: "M1211398804RE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1211398804RE.IMG",
		ResolutionM: 0.61, DEMTile: "SLDEM2015_512_00N_10N_045_090", SPICEKernel: "lro_frames_2024_v01.tf",
		CraterID: "LU_00055102", DiameterKm: 4.7},
	{ID: "site-006", SiteType: "polar", Latitude: -88.20, Longitude: 0.00,
		PradanImageID: "ch2_ohr_ncp_20240110T0642331120_d_img_d31",
		ODEProductID: "M1339971716LE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1339971716LE.IMG",
		ResolutionM: 1.75, DEMTile: "LOLA_SPOLE_60S_5MPP", SPICEKernel: "moon_pa_de440_200625.bpc",
		CraterID: "LU_00090044", DiameterKm: 21.4},
	{ID: "site-007", SiteType: "polar", Latitude: -85.60, Longitude: 120.40,
		PradanImageID: "ch2_ohr_ncp_20240213T1102217753_d_img_d07",
		ODEProductID: "M1122837291RE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1122837291RE.IMG",
		ResolutionM: 1.40, DEMTile: "LOLA_SPOLE_60S_5MPP", SPICEKernel: "moon_080317.tf",
		CraterID: "LU_00033215", DiameterKm: 8.6},
	{ID: "site-008", SiteType: "polar", Latitude: 87.90, Longitude: 200.10,
		PradanImageID: "ch2_ohr_ncp_20240307T0225589931_d_img_d25",
		ODEProductID: "M1298450317LE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1298450317LE.IMG",
		ResolutionM: 1.88, DEMTile: "LOLA_NPOLE_60N_5MPP", SPICEKernel: "lro_frames_2024_v01.tf",
		CraterID: "LU_00061187", DiameterKm: 14.2},
	{ID: "site-009", SiteType: "polar", Latitude: -89.10, Longitude: 310.50,
		PradanImageID: "ch2_ohr_ncp_20240429T1934405512_d_img_d19",
		ODEProductID: "M1180209643RE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1180209643RE.IMG",
		ResolutionM: 1.62, DEMTile: "LOLA_SPOLE_60S_5MPP", SPICEKernel: "de440s.bsp",
		CraterID: "LU_00027754", DiameterKm: 2.5},
	{ID: "site-010", SiteType: "polar", Latitude: 84.30, Longitude: 55.70,
		PradanImageID: "ch2_ohr_ncp_20240508T0817263340_d_img_d33",
		ODEProductID: "M1265539871LE", ODEImageURL: "https://ode.rsl.wustl.edu/moon/img/M1265539871LE.IMG",
		ResolutionM: 1.55, DEMTile: "LOLA_NPOLE_60N_5MPP", SPICEKernel: "moon_pa_de440_200625.bpc",
		CraterID: "LU_00084456", DiameterKm: 11.9},
}

// rng is seeded once so repeated calls actually vary within a process run.
var rng = rand.New(rand.NewSource(time.Now().UnixNano()))

// RandomResult returns one hardcoded entry chosen at random.
func RandomResult() SiteResult {
	return mockPool[rng.Intn(len(mockPool))]
}

// RandomN returns n entries in random order (n is clamped to the pool size).
// Use n=10 to get the whole pool shuffled.
func RandomN(n int) []SiteResult {
	if n > len(mockPool) || n < 0 {
		n = len(mockPool)
	}
	shuffled := make([]SiteResult, len(mockPool))
	copy(shuffled, mockPool)
	rng.Shuffle(len(shuffled), func(i, j int) {
		shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
	})
	return shuffled[:n]
}

// All returns all 10 entries in their fixed order (no randomization).
func All() []SiteResult {
	return mockPool
}
