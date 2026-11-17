# Controller workspace and ground-data feasibility

Updated 12 November 2026. The dashboard has Tower, Ground and Clearance position views over one shared backend session. These tabs do not implement separate authenticated controllers or transfer control ownership.

## Screen and backend connections

- Flight strips use the existing aircraft WebSocket feed and HTTP polling fallback. Search covers callsign, route and ICAO24.
- Tower shows the shared traffic picture and conflict assistance. Ground strips select only `onGround === true`; the map retains surrounding airborne traffic for context.
- Clearance prioritises communications. Selecting a strip opens details alongside the map; switching position keeps the selection.
- Aircraft identity, observed altitude/speed, route lookup provenance and derived phase are labelled separately. Route lookup is not a filed flight plan.
- Recorded airborne instructions use POST /api/clearances. The returned application result is shown. This does not transmit a clearance. Ground aircraft cannot receive this airborne instruction form.
- Predictions continue through /api/aircraft/trajectory. AI decisions use the existing accept/dismiss endpoints; audit uses /api/audit. Position switches are logged.
- Weather and runway information continue through /api/airport. Global conflict alerts remain visible in every position.
- There is no taxi-route clearance, pushback approval, runway crossing authorization, stop-bar control or real handoff backend. These are not presented as working controls.

## Ground data: possible, but coverage must be measured

1. OpenSky state vectors include on-ground state and coordinates when available. Bounding-box requests can capture surface reports. They do not supply a complete airport ground picture, operational clearances or filed routes. REST currently excludes MLAT positions. [API documentation](https://openskynetwork.github.io/opensky-api/rest.html).
2. adsb.lol publishes received aircraft messages via API and historical archives. It is a candidate for supplemental surface reports; permission/keys, limits and ODbL attribution must be checked for the intended use. [API](https://www.adsb.lol/docs/open-data/api), [provider overview](https://www.adsb.lol/about).
3. A local ADS-B receiver with suitable airport visibility is another acquisition path. Availability still depends on transmissions, receiver placement and line of sight. It cannot guarantee all vehicles or aircraft are detected.
4. Operational surface systems combine radar, multilateration and ADS-B. Their feeds require arrangements with the airport/provider; no public Mumbai A-SMGCS feed was established by this research. [FAA surveillance description](https://www.faa.gov/air_traffic/publications/atpubs/aim_html/chap4_section_5.html).

The project normalizer already carries onGround for live OpenSky reports. However, replay_service.py explicitly removes ground rows. The bundled replay is airborne only. The Ground view therefore explains an empty feed rather than suggesting a clear runway. No new public provider was silently substituted and no live Mumbai ground-coverage measurement was performed in this UI task.

Next acquisition work should sample a provider over a representative operating period, measure fresh surface coordinates and gaps, retain source/position timestamps, and distinguish unknown state from airborne. Surface records should enter a separate surface-history pipeline before considering taxi predictions; the existing airborne models must not be represented as validated ground-conflict models. Airport diagrams alone are static geometry, not ground traffic.

## Design references

- [EUROCONTROL illustrated tower interface](https://www.eurocontrol.int/sites/default/files/2020-10/eurocontrol-itwp-baseline-hmi-description-v1.0.pdf): flight strip bays and role-based controls.
- [EASA workstation study](https://www.easa.europa.eu/en/downloads/141853/en): separate tower/approach roles, communications and outside view.
- [NAVCANsuite](https://www.navcanatm-navcangca.ca/en/enterprise-atm-technology/navcansuite.aspx): integrated or multiple-display layouts.

This implementation reuses existing APIs and model behavior. Familiarity for operational controllers has not been validated through user trials. Browser visual QA was attempted but the browser access host was unavailable.
