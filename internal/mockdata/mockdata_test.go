package mockdata

import "testing"

func TestAllReturnsTenEntries(t *testing.T) {
all := All()
if len(all) != 10 {
t.Fatalf("expected 10 entries, got %d", len(all))
}
seen := map[string]bool{}
for _, r := range all {
if r.ID == "" {
t.Error("entry has empty ID")
}
if seen[r.ID] {
t.Errorf("duplicate ID in pool: %s", r.ID)
}
seen[r.ID] = true
if r.SiteType != "equatorial" && r.SiteType != "polar" {
t.Errorf("unexpected SiteType %q for %s", r.SiteType, r.ID)
}
if r.DiameterKm <= 0 {
t.Errorf("expected positive DiameterKm for %s, got %v", r.ID, r.DiameterKm)
}
}
}

func TestRandomResultReturnsPoolMember(t *testing.T) {
valid := map[string]bool{}
for _, r := range All() {
valid[r.ID] = true
}
for i := 0; i < 50; i++ {
got := RandomResult()
if !valid[got.ID] {
t.Fatalf("RandomResult returned unknown ID %q", got.ID)
}
}
}

func TestRandomResultVariesAcrossCalls(t *testing.T) {
seen := map[string]bool{}
for i := 0; i < 200; i++ {
seen[RandomResult().ID] = true
if len(seen) > 1 {
return
}
}
t.Fatal("RandomResult returned the same entry 200 times in a row; randomization may be broken")
}

func TestRandomNCounts(t *testing.T) {
cases := []struct {
name    string
n       int
wantLen int
}{
{"zero", 0, 0},
{"partial", 5, 5},
{"exact", 10, 10},
{"over_clamped", 15, 10},
{"negative_clamped", -1, 10},
}
for _, tc := range cases {
t.Run(tc.name, func(t *testing.T) {
got := RandomN(tc.n)
if len(got) != tc.wantLen {
t.Errorf("RandomN(%d) returned %d entries, want %d", tc.n, len(got), tc.wantLen)
}
})
}
}

func TestRandomNNoDuplicates(t *testing.T) {
got := RandomN(10)
seen := map[string]bool{}
for _, r := range got {
if seen[r.ID] {
t.Errorf("RandomN(10) produced duplicate ID %s", r.ID)
}
seen[r.ID] = true
}
}
