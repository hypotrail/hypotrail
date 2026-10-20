# Third-party data and references

## UCI Bank Marketing

- Dataset: Bank Marketing, UCI Machine Learning Repository.
- Attribution: Moro, S., Rita, P., and Cortez, P. (2014).
- DOI: `10.24432/C5K306`.
- Source: [UCI Bank Marketing](https://archive.ics.uci.edu/dataset/222/bank+marketing)
- Dataset license recorded by the source: CC BY 4.0.
- Included extract: `use-cases/bank-marketing/data/bank.csv`, with source documentation in `bank-names.txt`.

The source data is retained without modification. Splits, predictions, charts, and tutorial outputs are derived exploratory teaching artifacts, not original dataset documentation.

### Full file (`bank-full.csv`)

- Included file: `use-cases/bank-marketing-full/data/bank-full.csv` (45,211 rows), with the same `bank-names.txt`, byte for byte.
- Obtained on 2026-10-19 from two public GitHub mirrors with identical bytes (`PacktWorkshops/The-Data-Science-Workshop`, `fenago/datasets`), because the UCI site was not reachable from the preparation environment. sha256 `d1513ec63b385506f7cfce9f2c5caa9fe99e7ba4e8c3fa264b3aaf0f849ed32d`. Verified against the figures UCI publishes (rows, columns, class counts) and against `bank.csv` (every row contained); not compared byte for byte with the UCI archive. See `use-cases/bank-marketing-full/README.md`.

## Hotel booking demand datasets

- Dataset: Hotel booking demand datasets, H1 (Resort Hotel) only; the article also describes H2 (City Hotel), which is not included.
- Attribution: Antonio, N., de Almeida, A., and Nunes, L. Hotel booking demand datasets. Data in Brief 22, 41–49 (2019).
- DOI: `10.1016/j.dib.2018.11.126` (article; PubMed Central PMC6297060).
- Licence: CC BY 4.0, the licence of the open-access article the data are supplied with. A separate wording for the data files was not read from the preparation environment.
- Included file: `use-cases/hotel-booking/data/hotel-resort.csv` (40,060 rows), **derived**: the Resort Hotel rows of the tidytuesday mirror (`rfordatascience/tidytuesday`, `data/2020/2020-02-11/hotels.csv`, sha256 `7c2ae42a7353905ea136e5c2287f17c92c5435826598bfbb8491c6f0c7b1fc06`, which combines both hotels, adds a `hotel` column and converts the column names to snake case), without the `hotel` column and sorted by arrival date; cell values unchanged. Obtained on 2026-10-20 because the authors' files were not reachable from the preparation environment; checked against the counts the article publishes, not compared byte for byte with the authors' files. Variable descriptions are taken from the tidytuesday data dictionary, which credits the article. See `use-cases/hotel-booking/README.md`.

## UCI Online Shoppers Purchasing Intention

- Dataset: Online Shoppers Purchasing Intention Dataset, UCI Machine Learning Repository (id 468).
- Attribution: Sakar, C. O., Polat, S. O., Katircioglu, M., and Kastro, Y. Real-time prediction of online shoppers' purchasing intention using multilayer perceptron and LSTM recurrent neural networks. Neural Computing and Applications 31, 6893–6908 (2019).
- DOI: `10.24432/C5F88Q` (dataset), `10.1007/s00521-018-3523-0` (article).
- Source: [UCI Online Shoppers Purchasing Intention](https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset)
- Dataset license recorded by the source: CC BY 4.0.
- Included file: `use-cases/online-shoppers/data/online_shoppers_intention.csv`, unmodified (CRLF line ends kept).
- Obtained on 2026-10-19 from a public GitHub mirror (`fenago/datasets`), because the UCI site was not reachable from the preparation environment. sha256 `b3055ee355f59134d851d32641183cb4a8b45def7124d2f50442a042f358e0d9`. Verified against the figures UCI publishes (12,330 rows, 18 columns, 1,908 sessions with a purchase); not compared byte for byte with the UCI archive. The DOIs and licence above were not re-checked from that environment. See `use-cases/online-shoppers/README.md`.

## UCI Auto MPG

- Dataset: Auto MPG, UCI Machine Learning Repository.
- Attribution: Quinlan, R. (1993).
- DOI: `10.24432/C5859H`.
- Source: [UCI Auto MPG](https://archive.ics.uci.edu/dataset/9/auto+mpg)
- Dataset license recorded by the source: CC BY 4.0.
- Included files and original documentation: `use-cases/auto-mpg/data/`.

The source data and documentation are preserved in their original form. Preparation, model comparisons, and EDA are derived exploratory artifacts.

## Project and dependencies

The framework was imported from the owner's earlier local Hypotrail development work. No project license is selected by this import. Third-party datasets retain their own attribution and terms. Python and JavaScript dependencies are not vendored; consult their respective distributions for licenses.
