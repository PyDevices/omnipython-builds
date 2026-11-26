# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""A browser page's ``espdl``: object detection through ONNX Runtime Web.

On a board ``espdl`` is the vision module's ESP-DL binding. In the all-apps
page this module gives the same ``YOLO11`` class, so the Detect app runs
unchanged::

    import espdl, image

    det = espdl.YOLO11("/models/yolo11n_coco.espdl", score=0.15)
    img = image.Image(320, 240, image.RGB565, buffer=buf)
    for x, y, w, h, score, cls in det.detect(img):
        ...
    det.deinit()

The page's ``/models/yolo11n_coco.espdl`` isn't ESP-DL's model. It is a short
JSON note that says where the page's ONNX model is (``url``, relative to the
page), its size (``bytes``), its SHA-256 (``sha256``), the side of the square
it looks at (``input``), and what it is (``model``, ``license``). The page
carries Megvii's YOLOX-nano (Apache-2.0), which knows the same 80 COCO classes
as the board's YOLO11n, so the boxes it finds may differ from a board's. The
page fetches the model the first time a detector opens, saying so on screen,
and the browser keeps it. The page's ``detect.mjs`` runs it with ONNX Runtime
Web, on WebGPU, WebGL or the CPU, whichever works first.

ESP-DL's other detectors and classifiers aren't here.
"""

import json

import _wasm_bridge
import image
import js
import jsffi

#: How long, in milliseconds, opening a detector may take: the model's
#: download and ONNX Runtime's start.
OPEN_MS = 300000

_STEP_MS = 20

GRAYSCALE = image.GRAYSCALE

_LOAD = """() => {
    const g = globalThis;
    if (g.omnipythonDetect) return {state: "ready", api: g.omnipythonDetect, error: ""};
    if (!g.__omnipythonDetectLoad) {
        const load = {state: "loading", api: null, error: ""};
        g.__omnipythonDetectLoad = load;
        const base = (g.document && g.document.baseURI) || (g.location && g.location.href);
        import(new URL("detect.mjs", base).href).then(
            () => { load.api = g.omnipythonDetect; load.state = "ready"; },
            (e) => { load.error = String(e); load.state = "failed"; g.__omnipythonDetectLoad = null; });
    }
    return g.__omnipythonDetectLoad;
}"""


def _wait(test, ms, step=_STEP_MS, deliver=True):
    waited = 0
    while not test():
        if waited >= ms:
            return False
        _wasm_bridge.sleep_ms(step, deliver)
        waited += step
    return True


def _page():
    """The page's detect.mjs, imported the first time."""
    load = js.eval(_LOAD)()
    _wait(lambda: str(load.state) != "loading", OPEN_MS)
    if str(load.state) != "ready":
        raise OSError("this page has no object detection: %s" % (load.error,))
    return load.api


def _spec(path):
    try:
        with open(path) as f:
            spec = json.load(f)
    except ValueError:
        raise OSError("%s is a board's model; in a browser it must be the page's note of where the ONNX model is" % path)
    if not isinstance(spec, dict) or "url" not in spec:
        raise OSError("%s doesn't say where the model is" % path)
    return spec


class YOLO11:
    """Object detection, the 80 COCO classes, as a board's ``YOLO11`` gives it.

    The page runs YOLOX-nano, so its boxes can differ a little from a
    board's; `model` says which model it is.

    Args:
        path: the page's note of where the model is
            (``/models/yolo11n_coco.espdl``).
        score: the lowest confidence kept, 0.25 when None.
        nms: the overlap above which a weaker box of the same class goes,
            0.45 when None.
        topk: the most detections a frame returns.
        mean: taken for a board's preprocessing, and ignored.
        std: taken for a board's preprocessing, and ignored.

    Raises:
        OSError: the note isn't there or says nothing, the model didn't
            download, or no way to run it worked; the message says which.
    """

    def __init__(self, path, *, score=None, nms=None, topk=10, mean=None, std=None):
        spec = _spec(path)
        self._score = 0.25 if score is None else float(score)
        self._nms = 0.45 if nms is None else float(nms)
        #: The model that runs, for a label.
        self.model = "YOLOX-nano"
        self._h = _page().open(json.dumps(spec), self._score, self._nms, int(topk))
        h = self._h
        if not _wait(lambda: str(h.state) != "loading", OPEN_MS):
            h.close()
            raise OSError("the model didn't load in %d s" % (OPEN_MS // 1000))
        if str(h.state) != "ready":
            raise OSError(str(h.error))
        #: Where it runs: "webgpu", "webgl" or "wasm".
        self.provider = str(h.provider)

    def detect(self, image):
        """Detect objects in *image*, an RGB565 or grayscale `image.Image`.

        Returns:
            ``[(x, y, w, h, score, class), ...]``, best first, in *image*'s
            pixels.
        """
        h = self._h
        if h is None:
            raise OSError("the detector is closed")
        h.run(jsffi.to_js(image.bytearray()), image.width(), image.height(), image.format() == GRAYSCALE)
        # No timer runs while the model looks, as none runs inside a board's
        # detect: the screen mustn't refresh from a frame the program has yet
        # to draw its boxes on.
        _wait(lambda: not h.busy, OPEN_MS, 1, False)
        if str(h.error):
            raise OSError(str(h.error))
        return [tuple(d) for d in json.loads(str(h.result))]

    def set_thresholds(self, *, score=None, nms=None):
        """Change the score or overlap thresholds; None keeps one."""
        if score is not None:
            self._score = self._h.score = float(score)
        if nms is not None:
            self._nms = self._h.nms = float(nms)
        return self

    def deinit(self):
        """Let the model go."""
        h, self._h = self._h, None
        if h is not None:
            h.close()

    __del__ = deinit
