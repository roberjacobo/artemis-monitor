use pyo3::prelude::*;
use pyo3::types::PyList;
use quick_xml::Reader;
use quick_xml::events::Event;

#[derive(Debug)]
struct DishStatus {
    name: String,
    azimuth: f64,
    elevation: f64,
    targets: Vec<String>,
}

fn parse_dsn_xml(xml: &str) -> Vec<DishStatus> {
    let mut reader = Reader::from_str(xml);
    reader.config_mut().trim_text(true);

    let mut dishes: Vec<DishStatus> = Vec::new();
    let mut current_dish: Option<DishStatus> = None;

    loop {
        match reader.read_event() {
            Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => match e.name().as_ref() {
                b"dish" => {
                    let mut name = String::new();
                    let mut azimuth = 0.0f64;
                    let mut elevation = 0.0f64;

                    for attr in e.attributes().flatten() {
                        match attr.key.as_ref() {
                            b"name" => name = String::from_utf8_lossy(&attr.value).to_string(),
                            b"azimuthAngle" => {
                                azimuth =
                                    String::from_utf8_lossy(&attr.value).parse().unwrap_or(0.0)
                            }
                            b"elevationAngle" => {
                                elevation =
                                    String::from_utf8_lossy(&attr.value).parse().unwrap_or(0.0)
                            }
                            _ => {}
                        }
                    }

                    current_dish = Some(DishStatus {
                        name,
                        azimuth,
                        elevation,
                        targets: Vec::new(),
                    });
                }
                b"target" => {
                    if let Some(ref mut dish) = current_dish {
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"name" {
                                let target = String::from_utf8_lossy(&attr.value).to_string();
                                if !target.is_empty() && target != "none" {
                                    dish.targets.push(target);
                                }
                            }
                        }
                    }
                }
                _ => {}
            },
            Ok(Event::End(ref e)) => {
                if e.name().as_ref() == b"dish" {
                    if let Some(dish) = current_dish.take() {
                        dishes.push(dish);
                    }
                }
            }
            Ok(Event::Eof) => break,
            Err(_) => break,
            _ => {}
        }
    }

    dishes
}

#[pyfunction]
fn parse_dsn<'py>(py: Python<'py>, xml: &str) -> PyResult<Bound<'py, PyList>> {
    let dishes = parse_dsn_xml(xml);
    let list = PyList::empty(py);

    for dish in dishes {
        let dict = pyo3::types::PyDict::new(py);
        dict.set_item("name", &dish.name)?;
        dict.set_item("azimuth", dish.azimuth)?;
        dict.set_item("elevation", dish.elevation)?;

        let targets = PyList::new(py, &dish.targets)?;
        dict.set_item("targets", targets)?;

        list.append(dict)?;
    }

    Ok(list)
}

#[pymodule]
fn dsn_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_dsn, m)?)?;
    Ok(())
}
