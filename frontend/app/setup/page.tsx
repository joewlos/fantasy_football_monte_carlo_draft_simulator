import { Link } from "@nextui-org/link";

import { title, subtitle } from "@/components/primitives";

export default function SetupPage() {
  return (
    <section className="flex flex-col items-center justify-center gap-8 py-8 md:py-10">
      <div className="inline-block max-w-lg text-center justify-center">
        <h1 className={title()}>{`Configure settings for a new draft.`}</h1>
        <h2 className={subtitle()}>
          Upload your {`league's`} teams and draft order, player projections,
          and historical draft data. Once your settings are configured,
          {`you'll`} be ready to{" "}
          <Link className={"text-lg lg:text-xl"} href="/draft">
            enter your draft room
          </Link>
          .
        </h2>
      </div>
    </section>
  );
}
