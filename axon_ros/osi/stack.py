"""Utility classes that keep track of which components populate each OSI layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

from .layers import OsiLayer


@dataclass
class OsiComponent:
    """Metadata describing a single runtime component within the stack."""

    name: str
    layer: OsiLayer
    instance: Any
    description: str | None = None

    def summary(self) -> str:
        """Return a human-readable description for logging/debugging."""

        suffix = f" — {self.description}" if self.description else ""
        return f"{self.name}{suffix}"


@dataclass
class OsiStack:
    """Registry of components organized by OSI layers."""

    label: str
    _components: Dict[OsiLayer, List[OsiComponent]] = field(
        default_factory=lambda: {layer: [] for layer in OsiLayer}
    )

    def register(
        self,
        layer: OsiLayer,
        name: str,
        instance: Any,
        *,
        description: str | None = None,
    ) -> OsiComponent:
        """Register *instance* under *layer* for documentation/inspection."""

        component = OsiComponent(name=name, layer=layer, instance=instance, description=description)
        self._components.setdefault(layer, []).append(component)
        return component

    def iter_layer(self, layer: OsiLayer) -> Iterable[OsiComponent]:
        return tuple(self._components.get(layer, ()))

    def __iter__(self) -> Iterable[tuple[OsiLayer, List[OsiComponent]]]:
        for layer in OsiLayer:
            yield layer, list(self._components.get(layer, ()))


def describe_stack(stack: OsiStack) -> str:
    """Return a formatted multi-line string summarizing *stack*."""

    lines: List[str] = [f"OSI stack — {stack.label}"]
    for layer, components in stack:
        if not components:
            continue
        lines.append(f"  {layer.name.title()}")
        for component in components:
            lines.append(f"    • {component.summary()}")
    return "\n".join(lines)
