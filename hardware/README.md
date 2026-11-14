# Ultraviolet hardware

Soil-moisture sensor nodes (ESP32 + capacitive/resistive soil probe) that stream readings into the app at `#/sensors`.

## How data flows

```
ESP32 node ──USB serial──▶ hardware/bridge/serial-bridge.mjs ──POST──▶ /api/sensors/readings ──SSE──▶ #/sensors page
```

The app keeps the latest 2,000 readings in memory and appends every reading to `runtime/sensors.jsonl`.

## Run it

1. Start the app: `npm run dev`
2. Plug the ESP32 into USB.
3. Run the bridge in a second terminal:

   ```sh
   npm run hardware:bridge
   # or pick the port and app URL yourself:
   node hardware/bridge/serial-bridge.mjs --port /dev/cu.usbserial-0001 --baud 115200 --app http://localhost:5173
   ```

4. Open `http://localhost:5173/#/sensors`.

The bridge auto-detects `/dev/cu.usbserial*`, `cu.SLAB_USBtoUART*`, `cu.wchusbserial*` and `cu.usbmodem*`. Close the Arduino Serial Monitor first, because only one program can hold the port.

## Firmware line format

The bridge parses either of these per line at 115200 baud:

```
[Node node-001] raw_AO=2310  soil=41.2%  wet=NO  DO=HIGH(dry)
{"nodeId":"node-002","soilPct":41.2,"rawAo":2310}
```

A line with `next in 30s` sets the reporting interval the page uses for its countdown. Other lines are echoed in the terminal for debugging.

## Sending readings without the bridge

A Wi-Fi node or gateway can POST directly:

```sh
curl -X POST http://<laptop-ip>:5173/api/sensors/readings \
  -H 'Content-Type: application/json' \
  -d '{"nodeId":"node-002","soilPct":41.2,"rawAo":2310,"source":"wifi"}'
```

## Reading the numbers

- `raw_AO` is the 12-bit ADC value (0–4095). Higher means drier on most probes.
- `raw_AO=4095` with `soil=0%` usually means the probe is in air or unplugged. The page shows a warning.
- The page labels below 20% as dry, 20–60% as good and above 60% as wet. Calibrate per probe by recording `raw_AO` in dry air and in a glass of water.
