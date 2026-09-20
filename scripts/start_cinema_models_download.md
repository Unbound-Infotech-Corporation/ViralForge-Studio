# ViralForge Cinema — model download

Preferred free open stack (local RTX 5090):

1. **Wan 2.2 I2V** hero shots — `Wan-AI/Wan2.2-I2V-A14B`
2. **LTX-2.5** AV bridges / extend — `Lightricks/LTX-2.5-Diffusers`
3. **Stitch** inside TrendForge (`concat_cut` / `concat_xfade`)

## Dry-run (no weights)

```bat
cd /d F:\ViralForge\VisualCreatorUnbound
python -m trendforge.cinema.download
```

## Fetch weights

```bat
cd /d F:\ViralForge\VisualCreatorUnbound
python -m trendforge.cinema.download --fetch
```

Weights land under `F:\TrendForge\models\cinema\` by default.

No Pinokio. No Maestro app. ViralForge Cinema is the native engine.
