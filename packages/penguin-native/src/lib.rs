use crc::Algorithm;
use pyo3::{prelude::*, sync::PyOnceLock};

const CRC_32_OGG: crc::Algorithm<u32> = Algorithm {
    width: 32,
    poly: 0x04c11db7,
    init: 0x00000000,
    refin: false,
    refout: false,
    xorout: 0x00000000,
    check: 0x89a1897f,
    residue: 0x00000000,
};
static CRC: PyOnceLock<crc::Crc<u32>> = PyOnceLock::new();

#[pyfunction]
#[pyo3(signature = (data, init = 0))]
fn crc32_ogg(data: &[u8], init: u32) -> u32 {
    let crc = Python::attach(|py| CRC.get_or_init(py, || crc::Crc::<u32>::new(&CRC_32_OGG)));
    let mut digest = crc.digest_with_initial(init);

    digest.update(data);
    digest.finalize()
}

/// A Python module implemented in Rust.
#[pymodule(name = "_native", gil_used = false)]
fn penguin_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(crc32_ogg, m)?)?;
    Ok(())
}
