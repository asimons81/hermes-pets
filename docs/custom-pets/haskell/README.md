# Haskell

Haskell is a custom Hermes Pets package based on Eric Fode's gray-brown tabby cat.
The package uses compact Codex/Hermes digital-pet style sprites with a complete
set of supported animation states.

## Identity notes

- Species: cat.
- Coat: gray-brown tabby with a light muzzle and expressive eyes.
- Anatomy: three-legged cat missing the anatomical front-right paw.
- Greeting: stands up on his back legs to say hi.

The original reference photo is not included in this repository. The submitted
sprites are generated/custom pet assets derived from a user-owned reference photo
and contributed with permission for redistribution in this repository.

## Included states

- `idle`
- `run_right`
- `run_left`
- `waving`
- `jumping`
- `failed`
- `waiting`
- `running`
- `review`

## Validation

```bash
hermes-pet custom-pet validate docs/custom-pets/haskell
hermes-pet custom-pet preview docs/custom-pets/haskell --output /tmp/haskell-preview.html
```

## License and attribution

Submitted by Eric Fode. The generated sprite/package files in this directory may
be redistributed with Hermes Pets under the repository license. The source photo
is private and intentionally omitted.
