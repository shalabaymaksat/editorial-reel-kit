"""Цвет. Қалыпты видео: скриншот берілсе соған сәйкестендіру, берілмесе түс өзгермейді.
S-Log3 (Sony) видео: алдымен S-Log3 -> Rec.709 базалық түрлендіру, сосын (бар болса) скриншотқа сәйкестендіру.

python3 grade.py base                                   -> luts/slog3_to_709.cube (бір рет, setup.sh жасайды)
python3 grade.py fit JOB --target ref.jpg [--t 10]      -> projects/JOB/grade.cube + check/grade_cmp.jpg
python3 grade.py fit JOB                                -> қалыпты видео: бірлік LUT (түс өзгермейді); S-Log3: базалық LUT

Скриншот сол бөлмеден болса (SIFT ≥ 20 сәйкестік) — кадрларды теңестіріп, полиномдық түс сәйкестендіру.
Басқа сахна болса — Lab кеңістігінде орта/дисперсия көшіру (жұмсағырақ).
"""
import argparse, json, os, subprocess, sys
import numpy as np
import cv2
from paths import FF, LUTS, job_dir, run

N = 33
# S-Gamut3.Cine -> Rec.709, сызықтық
M_SG3C_709 = np.array([[1.6269474, -0.5401385, -0.0868089],
                       [-0.1785155, 1.4179409, -0.2394254],
                       [-0.0444361, -0.1959199, 1.2403560]])


def slog3_decode(rgb):
    cv = (rgb * 876 + 64) / 1023  # ffmpeg tv->pc кеңейтуін кері қайтару: 10-бит код мәні / 1023
    hi = cv >= 171.2102946929 / 1023
    lin = np.where(hi, 10 ** ((cv * 1023 - 420) / 261.5) * (0.18 + 0.01) - 0.01,
                   (cv * 1023 - 95) * 0.01125 / (171.2102946929 - 95))
    return lin


def filmic(x, exposure=0.8):
    x = np.maximum(x * exposure, 0)
    y = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    return np.clip(y, 0, 1) ** (1 / 2.2)


def grid():
    r = np.linspace(0, 1, N)
    b, g, rr = np.meshgrid(r, r, r, indexing='ij')  # .cube: R ең жылдам өзгереді
    return np.stack([rr, g, b], -1).reshape(-1, 3)


def base_map(rgb, log='slog3'):
    if log == 'none':
        return rgb
    lin = slog3_decode(rgb) @ M_SG3C_709.T
    return filmic(lin)


def write_cube(path, rgb_out, title):
    with open(path, 'w') as f:
        f.write(f'TITLE "{title}"\nLUT_3D_SIZE {N}\n')
        np.savetxt(f, np.clip(rgb_out, 0, 1), fmt='%.6f')


def feats(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    return np.stack([np.ones_like(r), r, g, b, r * r, g * g, b * b, r * g, r * b, g * b, r ** 3, g ** 3, b ** 3], -1)


def fit_poly(X, Y):
    """Сенімді (робаст) полиномдық сәйкестендіру; бірлік түрлендіруге қарай регуляризация."""
    F = feats(X)
    prior = np.zeros((13, 3)); prior[1, 0] = prior[2, 1] = prior[3, 2] = 1
    W = np.ones(len(X)); lam = 1e-5 * len(X)
    for _ in range(6):
        Fw = F * W[:, None]
        C = np.linalg.solve(F.T @ Fw + lam * np.eye(13), F.T @ (Y * W[:, None]) + lam * prior)
        e = np.linalg.norm(F @ C - Y, axis=1)
        W = .03 / np.maximum(e, .03)
    return C


def frame_at(video, t, lut=None):
    vf = f'lut3d={lut},' if lut else ''
    out = subprocess.run([FF, '-v', 'error', '-ss', str(t), '-i', video, '-frames:v', '1',
                          '-vf', vf + 'format=bgr24', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    from paths import probe
    w, h, *_ = probe(video)
    return np.frombuffer(out, np.uint8).reshape(h, w, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd'); ap.add_argument('job', nargs='?')
    ap.add_argument('--target'); ap.add_argument('--t', type=float, default=None)
    ap.add_argument('--log', default=None, help='slog3 | none (әдепкі: meta.json-нан)')
    a = ap.parse_args()
    os.makedirs(LUTS, exist_ok=True)
    G = grid()
    if a.cmd == 'base':
        write_cube(f'{LUTS}/slog3_to_709.cube', base_map(G), 'S-Log3 SGamut3.Cine to Rec709 (filmic)')
        print(f'{LUTS}/slog3_to_709.cube')
        return
    J = job_dir(a.job)
    meta = json.load(open(f'{J}/meta.json'))
    log = a.log or meta.get('log', 'none')
    t = a.t if a.t is not None else meta['duration'] / 2
    os.makedirs(f'{J}/check', exist_ok=True)
    base = base_map(G, log)
    if not a.target:
        write_cube(f'{J}/grade.cube', base, 'base')
        print('grade.cube = базалық LUT', log)
        return
    base_cube = f'{J}/_base.cube'
    write_cube(base_cube, base, 'base')
    src = frame_at(meta['camera'], t, base_cube)
    T = cv2.imread(a.target)
    if T is None:
        sys.exit(f'!! сурет оқылмады: {a.target} (jpg/png керек; видеодан кадр алу: ffmpeg -ss 5 -i v.mp4 -frames:v 1 ref.jpg)')
    sift = cv2.SIFT_create(6000)
    kt, dt = sift.detectAndCompute(cv2.cvtColor(T, cv2.COLOR_BGR2GRAY), None)
    ks, ds = sift.detectAndCompute(cv2.cvtColor(src, cv2.COLOR_BGR2GRAY), None)
    good = [m for m, n in cv2.BFMatcher().knnMatch(dt, ds, k=2) if m.distance < .75 * n.distance] if dt is not None and ds is not None else []
    A, inl = (None, None)
    if len(good) >= 8:
        A, inl = cv2.estimateAffinePartial2D(np.float32([ks[m.trainIdx].pt for m in good]),
                                             np.float32([kt[m.queryIdx].pt for m in good]), ransacReprojThreshold=4)
    ninl = int(inl.sum()) if inl is not None else 0
    bl = lambda x: cv2.GaussianBlur(x, (0, 0), 5).astype(np.float64)[..., ::-1] / 255  # RGB
    if A is not None and ninl >= 20:
        h, w = T.shape[:2]
        ws = cv2.warpAffine(src, A, (w, h), flags=cv2.INTER_AREA)
        valid = cv2.warpAffine(np.ones(src.shape[:2], np.uint8), A, (w, h)) > 0
        X, Y = bl(ws)[valid], bl(T)[valid]
        C = fit_poly(X[::4], Y[::4])
        out = np.clip(feats(np.clip(base, 0, 1)) @ C, 0, 1)
        mode = f'сол сахна: {ninl} сәйкестік, полином'
        pred = (np.clip(feats(ws[..., ::-1] / 255.) @ C, 0, 1)[..., ::-1] * 255).astype(np.uint8)
        cmp = np.hstack([ws, pred, T])
    else:
        # басқа сахна: Lab орта/дисперсия көшіру
        to_lab = lambda bgr: cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
        Ls, Lt = to_lab(src), to_lab(T)
        ms, ss, mt, st = Ls.mean(0), Ls.std(0) + 1e-6, Lt.mean(0), Lt.std(0)
        # жұмсақ: жарықтық толық, түс реңкі жартылай көшеді (басқа сахнадан қатты реңк кірмесін)
        k = np.clip(st / ss, .8, 1.25)
        k[1:] = 1 + (k[1:] - 1) * .5
        mt = ms + (mt - ms) * np.array([1.0, .45, .45])
        cube_bgr = (base[:, ::-1] * 255).astype(np.uint8)[None]
        lab = cv2.cvtColor(cube_bgr, cv2.COLOR_BGR2LAB)[0].astype(np.float64)
        lab = (lab - ms) * k + mt
        out = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2BGR)[0][:, ::-1] / 255.
        mode = f'басқа сахна ({ninl} сәйкестік): Lab көшіру'
        h = 600
        rs = lambda im: cv2.resize(im, (int(im.shape[1] * h / im.shape[0]), h))
        lab_s = (cv2.cvtColor(src, cv2.COLOR_BGR2LAB).astype(np.float64) - ms) * k + mt
        pred = cv2.cvtColor(np.clip(lab_s, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
        cmp = np.hstack([rs(src), rs(pred), rs(T)])
    write_cube(f'{J}/grade.cube', out, 'matched')
    os.remove(base_cube)
    cv2.imwrite(f'{J}/check/grade_cmp.jpg', cmp)
    print(mode, '->', f'{J}/grade.cube', '| салыстыру: check/grade_cmp.jpg (база | нәтиже | мақсат)')


if __name__ == '__main__':
    main()
