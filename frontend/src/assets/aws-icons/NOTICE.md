# AWS Architecture Icons

These SVG files are official AWS Architecture Icons (service icons, 64 px set) from the
AWS Architecture Icons package, release **07/31/2026**, downloaded on 2026-11-19 from
<https://aws.amazon.com/architecture/icons/>
(`Icon-package_07312026.5846e92413caa21490223536cc97f1269e44fa92.zip`).

Only a subset is included: the services ArchonAI architectures commonly use. Each file is the
original `Architecture-Service-Icons_07312026/<category>/64/Arch_<Service>_64.svg`, renamed to a
short key (for example `Arch_AWS-Lambda_64.svg` → `lambda.svg`), with the XML declaration and the
internal `<title>` removed. Shapes, colours and proportions are unchanged.

AWS states on that page: "We allow customers and partners to use these toolkits and assets to
create architecture diagrams." ArchonAI uses them only for that purpose: the architecture
diagrams and service listings in the exported PDF report. AWS and the AWS service names and logos
are trademarks of Amazon.com, Inc. or its affiliates. Review AWS's current terms before
redistributing this repository publicly.

The mapping from service names to these files is in
`src/features/architectures/results/pdf/aws-icons.ts`.
